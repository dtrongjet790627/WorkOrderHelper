# -*- coding: utf-8 -*-
"""
从EAI日志提取报工成功记录并插入数据库 - 完整版
用途：连接163服务器，读取EAI日志，提取报工成功记录，去重后插入工厂库
作者：韩大师
日期：2026-01-19
"""

import re
import json
import subprocess
import cx_Oracle
from datetime import datetime
from collections import defaultdict

# 日志文件配置
LOG_FILES = {
    'dpeps1': '/var/eai/logs/FLOW_DP-EPS\\IPA MES报工接口.log',
    'dpepp1': '/var/eai/logs/FLOW_DP-SMT\\MID\\EPP MES报工接口.log',
    'smt2': '/var/eai/logs/FLOW_SMT\\MID-Line2MES报工接口.log',
}

# 数据库连接配置
DB_CONFIG = {
    'dpepp1': {
        'user': 'iplant_dpepp1',
        'password': 'acc',
        'dsn': '172.17.10.165:1521/orcl.ecdag.com',
        'name': '电控一线'
    },
    'smt2': {
        'user': 'iplant_smt2',
        'password': 'acc',
        'dsn': '172.17.10.165:1521/orcl.ecdag.com',
        'name': '电控二线'
    },
    'dpeps1': {
        'user': 'iplant_dpeps1',
        'password': 'acc',
        'dsn': '172.17.10.165:1521/orcl.ecdag.com',
        'name': '总成DP'
    }
}

def parse_timestamp(log_line):
    """从日志行提取时间戳"""
    match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', log_line)
    if match:
        return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
    return None

def parse_trigger_data(log_line):
    """从触发数据行提取JSON（仅用于获取LINE信息）"""
    match = re.search(r'db trigger get data:(\[.*?\])\s*$', log_line)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None

def parse_kingdee_request(log_line):
    """
    从金蝶请求行提取实际报工的数据
    注意：
    1. 日志中的data字段可能是被转义的JSON字符串，需要二次解析
    2. 日志行可能被截断，需要使用正则表达式提取关键字段
    """
    if 'kingdee request json:' not in log_line:
        return None

    # 方法1：尝试解析完整JSON
    match = re.search(r'kingdee request json:\s*(\{.*\})\s*$', log_line)
    if match:
        try:
            req = json.loads(match.group(1))
            data = req.get('data', {})

            # 处理data字段可能是字符串的情况（需要二次解析）
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    pass

            if isinstance(data, dict):
                model = data.get('Model', {})
                entities = model.get('FEntity', [])

                # 提取报工数据
                records = []
                for entity in entities:
                    lot = entity.get('FLot', {})
                    material = entity.get('FMaterialId', {})

                    record = {
                        'packid': lot.get('FNumber', ''),
                        'wono': entity.get('FMoBillNo', ''),
                        'partno': material.get('FNumber', ''),
                        'cnt': int(entity.get('FQuaQty', 0)),
                    }
                    if record['packid'] and record['wono']:
                        records.append(record)

                return records if records else None
        except json.JSONDecodeError:
            pass

    # 方法2：日志被截断时，使用正则表达式提取关键字段
    # PACKID格式：日期8位 + 字母 + 数字7位，如 20251208E2700121, 20260119I0900211
    packid_match = re.search(r'(\d{8}[A-Z]\d{7})', log_line)

    # 工单号格式：EPS+数字、MID-2+数字、EPP+数字、IPA+数字
    wono_match = re.search(r'FMoBillNo.*?(EPS\d+|MID-2\d+|EPP\d+|IPA\d+)', log_line)

    # 物料号格式：字母+数字.数字.数字
    partno_match = re.search(r'FMaterialId.*?FNumber.*?([A-Z]\d{2}\.\d{3}\.\d{3})', log_line)

    # 数量
    cnt_match = re.search(r'FQuaQty[^0-9]*(\d+)', log_line)

    if packid_match and wono_match:
        record = {
            'packid': packid_match.group(1),
            'wono': wono_match.group(1),
            'partno': partno_match.group(1) if partno_match else '',
            'cnt': int(cnt_match.group(1)) if cnt_match else 0,
        }
        return [record]

    return None

def parse_kingdee_response(log_line):
    """从金蝶响应行提取SCHB单号和是否成功"""
    match = re.search(r'kingdee response json:\s*(\{.*\})\s*$', log_line)
    if match:
        try:
            resp = json.loads(match.group(1))
            result = resp.get('Result', {})
            status = result.get('ResponseStatus', {})
            if status.get('IsSuccess'):
                # 提取SCHB单号
                schb_number = result.get('Number', '')
                return schb_number
        except json.JSONDecodeError:
            pass
    return None

def is_flow_success(log_line):
    """判断是否是流程成功行"""
    return 'run success' in log_line and 'flow' in log_line

def extract_line_from_trigger_data(trigger_data, packid):
    """从触发数据中查找对应PACKID的产线信息"""
    if not trigger_data:
        return ''
    for item in trigger_data:
        if item.get('PACKID') == packid:
            return item.get('LINE', '')
    # 如果没找到完全匹配，返回第一条的LINE
    if trigger_data:
        return trigger_data[0].get('LINE', '')
    return ''

def extract_records_from_content(content, line_code, start_date=None):
    """从日志内容提取报工成功记录"""
    records = []
    lines = content.split('\n')

    # 状态机变量
    current_trigger_data = None
    current_trigger_time = None
    current_request_data = None
    current_request_time = None
    current_schb_number = None

    for line in lines:
        ts = parse_timestamp(line)

        if ts and start_date and ts < start_date:
            continue

        # 检查触发数据
        trigger_data = parse_trigger_data(line)
        if trigger_data:
            current_trigger_data = trigger_data
            current_trigger_time = ts
            current_request_data = None
            current_schb_number = None
            continue

        # 检查金蝶请求
        request_data = parse_kingdee_request(line)
        if request_data:
            current_request_data = request_data
            current_request_time = ts
            continue

        # 检查金蝶响应
        schb = parse_kingdee_response(line)
        if schb:
            current_schb_number = schb
            continue

        # 检查流程成功
        if is_flow_success(line) and current_request_data and current_schb_number:
            for item in current_request_data:
                line_info = extract_line_from_trigger_data(current_trigger_data, item['packid'])

                record = {
                    'wono': item['wono'],
                    'packid': item['packid'],
                    'partno': item['partno'],
                    'cnt': item['cnt'],
                    'line': line_info,
                    'schb_number': current_schb_number,
                    'report_time': current_request_time or current_trigger_time,
                    'line_code': line_code
                }
                records.append(record)

            current_request_data = None
            current_schb_number = None

    return records

def read_log_from_163(log_path):
    """通过SSH从163服务器读取日志文件"""
    cmd = f'ssh -p 2200 root@172.17.10.163 "cat \'{log_path}\'"'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=120)
        if result.returncode == 0:
            # 尝试UTF-8解码，失败则用latin-1
            try:
                return result.stdout.decode('utf-8')
            except UnicodeDecodeError:
                return result.stdout.decode('latin-1', errors='ignore')
        else:
            print(f"  读取日志失败: {result.stderr.decode('utf-8', errors='ignore')}")
            return None
    except subprocess.TimeoutExpired:
        print(f"  读取日志超时")
        return None
    except Exception as e:
        print(f"  读取日志出错: {e}")
        return None

def get_existing_packids(conn, table_name='ACC_ERP_REPORT_SUCCESS'):
    """获取数据库中已存在的PACKID列表"""
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT PACKID FROM {table_name}")
    packids = set(row[0] for row in cursor.fetchall())
    cursor.close()
    return packids

def insert_records(conn, records, existing_packids):
    """插入新记录到数据库"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for record in records:
        if record['packid'] in existing_packids:
            skipped += 1
            continue

        try:
            # 使用序列生成ID
            sql = """
            INSERT INTO ACC_ERP_REPORT_SUCCESS (
                ID, WONO, PACKID, PARTNO, CNT, LINE, SCHB_NUMBER, REPORT_TIME, CREATETIME, IS_SUCCESS
            ) VALUES (
                ACC_ERP_REPT_SUCC_SEQ.NEXTVAL,
                :wono, :packid, :partno, :cnt, :line, :schb_number, :report_time, SYSDATE, 1
            )
            """
            cursor.execute(sql, {
                'wono': record['wono'],
                'packid': record['packid'],
                'partno': record['partno'],
                'cnt': record['cnt'],
                'line': record.get('line', ''),
                'schb_number': record['schb_number'],
                'report_time': record['report_time']
            })
            existing_packids.add(record['packid'])
            inserted += 1
        except cx_Oracle.IntegrityError as e:
            # 重复键错误，跳过
            skipped += 1
        except Exception as e:
            print(f"  插入失败: {e}")
            print(f"  记录: {record}")

    conn.commit()
    cursor.close()
    return inserted, skipped

def main():
    """主函数"""
    print("=" * 80)
    print("EAI日志报工数据提取与插入工具")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = {}

    for line_code, log_path in LOG_FILES.items():
        config = DB_CONFIG[line_code]
        print(f"\n[{config['name']}] ({line_code})")
        print("-" * 40)

        # 读取日志
        print(f"  读取日志: {log_path}")
        content = read_log_from_163(log_path)
        if not content:
            results[line_code] = {'status': 'error', 'msg': '读取日志失败'}
            continue

        # 提取记录
        print(f"  日志大小: {len(content)} 字符")
        records = extract_records_from_content(content, line_code)
        print(f"  提取记录: {len(records)} 条")

        if not records:
            results[line_code] = {'status': 'ok', 'extracted': 0, 'inserted': 0, 'skipped': 0}
            continue

        # 连接数据库
        try:
            conn = cx_Oracle.connect(f"{config['user']}/{config['password']}@{config['dsn']}")
            print(f"  数据库连接成功")
        except Exception as e:
            print(f"  数据库连接失败: {e}")
            results[line_code] = {'status': 'error', 'msg': str(e)}
            continue

        # 获取已存在的PACKID
        existing_packids = get_existing_packids(conn)
        print(f"  已存在PACKID: {len(existing_packids)} 个")

        # 插入新记录
        inserted, skipped = insert_records(conn, records, existing_packids)
        print(f"  新插入: {inserted} 条")
        print(f"  已存在跳过: {skipped} 条")

        conn.close()
        results[line_code] = {
            'status': 'ok',
            'extracted': len(records),
            'inserted': inserted,
            'skipped': skipped
        }

    # 打印汇总
    print("\n" + "=" * 80)
    print("执行汇总")
    print("=" * 80)
    total_extracted = 0
    total_inserted = 0
    total_skipped = 0
    for line_code, result in results.items():
        config = DB_CONFIG.get(line_code, {})
        name = config.get('name', line_code)
        if result['status'] == 'ok':
            print(f"  {name}: 提取 {result['extracted']} 条, 插入 {result['inserted']} 条, 跳过 {result['skipped']} 条")
            total_extracted += result['extracted']
            total_inserted += result['inserted']
            total_skipped += result['skipped']
        else:
            print(f"  {name}: 错误 - {result.get('msg', '未知错误')}")
    print("-" * 40)
    print(f"  总计: 提取 {total_extracted} 条, 插入 {total_inserted} 条, 跳过 {total_skipped} 条")

    return results

if __name__ == '__main__':
    main()

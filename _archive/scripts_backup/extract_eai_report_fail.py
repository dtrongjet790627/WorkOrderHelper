# -*- coding: utf-8 -*-
"""
从EAI日志提取报工失败记录并插入数据库
用途：连接163服务器，读取EAI日志，提取报工失败记录，按去重规则插入工厂库
作者：韩大师
日期：2026-01-19

去重规则：
1. 同一工单(WONO) + 同一批次(PACKID) + 相同错误信息，只插入第一条
2. 后续相同组合的失败记录不再插入
"""

import re
import json
import subprocess
import cx_Oracle
from datetime import datetime
from collections import defaultdict
import os
import gzip

# 日志文件配置
LOG_PATTERNS = {
    'dpeps1': ['FLOW_DP-EPS\\IPA MES报工接口', 'Flow DP-EPS\\IPA MES报工接口'],
    'dpepp1': ['FLOW_DP-SMT\\MID\\EPP MES报工接口', 'Flow DP-SMT\\MID\\EPP MES报工接口'],
    'smt2': ['FLOW_SMT\\MID-Line2MES报工接口', 'Flow SMT\\MID-Line2MES报工接口'],
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
    """从触发数据行提取JSON（用于获取LINE信息和触发批次）"""
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
    packid_match = re.search(r'(\d{8}[A-Z]\d{7})', log_line)
    wono_match = re.search(r'FMoBillNo.*?(EPS\d+|MID-2\d+|EPP\d+|IPA\d+)', log_line)
    partno_match = re.search(r'FMaterialId.*?FNumber.*?([A-Z]\d{2}\.\d{3}\.\d{3})', log_line)
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

def parse_kingdee_response_fail(log_line):
    """
    从金蝶响应行提取失败信息
    返回: (is_success, error_message)
    """
    match = re.search(r'kingdee response json:\s*(\{.*\})\s*$', log_line)
    if match:
        try:
            resp = json.loads(match.group(1))
            result = resp.get('Result', {})
            status = result.get('ResponseStatus', {})

            if status.get('IsSuccess'):
                # 成功
                schb_number = result.get('Number', '')
                return (True, schb_number, None)
            else:
                # 失败，提取错误信息
                errors = status.get('Errors', [])
                error_messages = []
                for err in errors:
                    msg = err.get('Message', '')
                    if msg:
                        error_messages.append(msg)
                error_message = '; '.join(error_messages) if error_messages else '未知错误'
                return (False, None, error_message)
        except json.JSONDecodeError:
            pass
    return None

def is_flow_failed(log_line):
    """判断是否是流程失败行"""
    return 'run failed' in log_line and 'flow' in log_line

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
    if trigger_data:
        return trigger_data[0].get('LINE', '')
    return ''

def extract_fail_records_from_content(content, line_code, start_date=None):
    """
    从日志内容提取报工失败记录

    返回: list of dict, 每条记录包含:
        - wono: 工单号
        - packid: 包装ID
        - partno: 物料号
        - cnt: 数量
        - line: 产线
        - error_message: 错误信息
        - report_time: 报工时间
    """
    records = []
    lines = content.split('\n')

    # 状态机变量
    current_trigger_data = None
    current_trigger_time = None
    current_request_data = None
    current_request_time = None
    current_error_message = None

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
            current_error_message = None
            continue

        # 检查金蝶请求
        request_data = parse_kingdee_request(line)
        if request_data:
            current_request_data = request_data
            current_request_time = ts
            continue

        # 检查金蝶响应
        response_result = parse_kingdee_response_fail(line)
        if response_result:
            is_success, schb_or_none, error_msg = response_result
            if not is_success:
                current_error_message = error_msg
            else:
                # 成功响应，清空错误信息
                current_error_message = None
            continue

        # 检查流程失败
        if is_flow_failed(line) and current_request_data and current_error_message:
            for item in current_request_data:
                line_info = extract_line_from_trigger_data(current_trigger_data, item['packid'])

                record = {
                    'wono': item['wono'],
                    'packid': item['packid'],
                    'partno': item['partno'],
                    'cnt': item['cnt'],
                    'line': line_info,
                    'error_message': current_error_message,
                    'report_time': current_request_time or current_trigger_time,
                    'line_code': line_code
                }
                records.append(record)

            # 重置状态
            current_request_data = None
            current_error_message = None

        # 检查流程成功（成功时清空状态）
        if is_flow_success(line):
            current_request_data = None
            current_error_message = None

    return records

def run_ssh_command(cmd, timeout=300):
    """执行SSH命令"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
        if result.returncode == 0:
            try:
                return result.stdout.decode('utf-8')
            except UnicodeDecodeError:
                return result.stdout.decode('latin-1', errors='ignore')
        return None
    except Exception as e:
        print(f"  SSH命令执行失败: {e}")
        return None

def list_log_files(pattern, start_date):
    """列出163服务器上符合条件的日志文件"""
    # 列出所有日志文件
    cmd = f'ssh -p 2200 root@172.17.10.163 "ls /var/eai/logs/ | grep -E \'MES报工\'"'
    result = run_ssh_command(cmd)
    if not result:
        return []

    all_files = result.strip().split('\n')
    matching_files = []

    for filename in all_files:
        # 检查是否匹配产线模式
        match_pattern = False
        for p in pattern:
            if p in filename:
                match_pattern = True
                break

        if not match_pattern:
            continue

        # 提取日期
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
        if date_match:
            file_date = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
            if file_date >= start_date:
                matching_files.append(filename)
        else:
            # 当前活动日志文件（无日期后缀）
            matching_files.append(filename)

    return matching_files

def read_log_file(filename):
    """从163服务器读取日志文件内容"""
    filepath = f'/var/eai/logs/{filename}'

    if filename.endswith('.gz'):
        cmd = f'ssh -p 2200 root@172.17.10.163 "zcat \'{filepath}\'"'
    else:
        cmd = f'ssh -p 2200 root@172.17.10.163 "cat \'{filepath}\'"'

    return run_ssh_command(cmd, timeout=300)

def deduplicate_fail_records(records):
    """
    对失败记录进行去重
    去重规则：同一工单(WONO) + 同一批次(PACKID) + 相同错误信息，只保留时间最早的一条
    """
    # 按 (WONO, PACKID, ERROR_MESSAGE) 分组
    groups = defaultdict(list)
    for record in records:
        key = (record['wono'], record['packid'], record['error_message'])
        groups[key].append(record)

    # 每组只保留时间最早的一条
    deduplicated = []
    for key, group_records in groups.items():
        # 按时间排序
        sorted_records = sorted(group_records, key=lambda x: x['report_time'] if x['report_time'] else datetime.max)
        deduplicated.append(sorted_records[0])

    return deduplicated

def get_existing_fail_keys(conn):
    """获取数据库中已存在的失败记录的 (WONO, PACKID, ERROR_MESSAGE) 组合"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT WONO, PACKID, ERROR_MESSAGE
        FROM ACC_ERP_REPORT_SUCCESS
        WHERE IS_SUCCESS = 0
    """)
    keys = set()
    for row in cursor.fetchall():
        wono = row[0] if row[0] else ''
        packid = row[1] if row[1] else ''
        error_msg = row[2] if row[2] else ''
        keys.add((wono, packid, error_msg))
    cursor.close()
    return keys

def insert_fail_records(conn, records, existing_keys):
    """插入失败记录到数据库"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for record in records:
        key = (record['wono'], record['packid'], record['error_message'])
        if key in existing_keys:
            skipped += 1
            continue

        try:
            sql = """
            INSERT INTO ACC_ERP_REPORT_SUCCESS (
                ID, WONO, PACKID, PARTNO, CNT, LINE, SCHB_NUMBER, REPORT_TIME, CREATETIME, IS_SUCCESS, ERROR_MESSAGE
            ) VALUES (
                ACC_ERP_REPT_SUCC_SEQ.NEXTVAL,
                :wono, :packid, :partno, :cnt, :line, NULL, :report_time, SYSDATE, 0, :error_message
            )
            """
            cursor.execute(sql, {
                'wono': record['wono'],
                'packid': record['packid'],
                'partno': record['partno'],
                'cnt': record['cnt'],
                'line': record.get('line', ''),
                'report_time': record['report_time'],
                'error_message': record['error_message'][:2000] if record['error_message'] else ''  # 限制长度
            })
            existing_keys.add(key)
            inserted += 1
        except cx_Oracle.IntegrityError as e:
            skipped += 1
        except Exception as e:
            print(f"  插入失败: {e}")
            print(f"  记录: WONO={record['wono']}, PACKID={record['packid']}")

    conn.commit()
    cursor.close()
    return inserted, skipped

def process_line(line_code, patterns, start_date):
    """处理单条产线的日志"""
    config = DB_CONFIG[line_code]
    print(f"\n[{config['name']}] ({line_code})")
    print("-" * 60)

    # 列出日志文件
    print(f"  查找日志文件...")
    log_files = list_log_files(patterns, start_date)
    print(f"  找到 {len(log_files)} 个日志文件")

    if not log_files:
        return {'status': 'ok', 'extracted': 0, 'deduplicated': 0, 'inserted': 0, 'skipped': 0}

    # 提取所有失败记录
    all_records = []
    for filename in log_files:
        print(f"  处理: {filename}")
        content = read_log_file(filename)
        if content:
            records = extract_fail_records_from_content(content, line_code, start_date)
            print(f"    提取失败记录: {len(records)} 条")
            all_records.extend(records)

    print(f"  总共提取失败记录: {len(all_records)} 条")

    if not all_records:
        return {'status': 'ok', 'extracted': 0, 'deduplicated': 0, 'inserted': 0, 'skipped': 0}

    # 去重
    deduplicated = deduplicate_fail_records(all_records)
    print(f"  去重后: {len(deduplicated)} 条")

    # 连接数据库
    try:
        conn = cx_Oracle.connect(f"{config['user']}/{config['password']}@{config['dsn']}")
        print(f"  数据库连接成功")
    except Exception as e:
        print(f"  数据库连接失败: {e}")
        return {'status': 'error', 'msg': str(e)}

    # 获取已存在的失败记录
    existing_keys = get_existing_fail_keys(conn)
    print(f"  已存在失败记录: {len(existing_keys)} 个")

    # 插入新记录
    inserted, skipped = insert_fail_records(conn, deduplicated, existing_keys)
    print(f"  新插入: {inserted} 条")
    print(f"  已存在跳过: {skipped} 条")

    conn.close()

    return {
        'status': 'ok',
        'extracted': len(all_records),
        'deduplicated': len(deduplicated),
        'inserted': inserted,
        'skipped': skipped
    }

def main():
    """主函数"""
    print("=" * 80)
    print("EAI日志报工失败记录提取与插入工具")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 从2025年10月1日开始提取
    start_date = datetime(2025, 10, 1)
    print(f"开始日期: {start_date.strftime('%Y-%m-%d')}")

    results = {}

    for line_code, patterns in LOG_PATTERNS.items():
        result = process_line(line_code, patterns, start_date)
        results[line_code] = result

    # 打印汇总
    print("\n" + "=" * 80)
    print("执行汇总")
    print("=" * 80)
    total_extracted = 0
    total_deduplicated = 0
    total_inserted = 0
    total_skipped = 0

    for line_code, result in results.items():
        config = DB_CONFIG.get(line_code, {})
        name = config.get('name', line_code)
        if result['status'] == 'ok':
            print(f"  {name}: 提取 {result['extracted']} 条, 去重后 {result['deduplicated']} 条, "
                  f"插入 {result['inserted']} 条, 跳过 {result['skipped']} 条")
            total_extracted += result['extracted']
            total_deduplicated += result['deduplicated']
            total_inserted += result['inserted']
            total_skipped += result['skipped']
        else:
            print(f"  {name}: 错误 - {result.get('msg', '未知错误')}")

    print("-" * 60)
    print(f"  总计: 提取 {total_extracted} 条, 去重后 {total_deduplicated} 条, "
          f"插入 {total_inserted} 条, 跳过 {total_skipped} 条")

    # 统计错误类型
    print("\n" + "=" * 80)
    print("错误类型统计")
    print("=" * 80)

    # 这里可以添加错误类型统计逻辑

    return results

if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""
从本地日志文件重新提取并导入报工成功记录 - 修复版
作者：韩大师
日期：2026-01-19
修复：处理JSON字符串嵌套问题
"""

import os
import json
import gzip
import re
import cx_Oracle
from datetime import datetime
from collections import defaultdict

# 本地日志目录
LOG_BASE_DIR = 'D:/TechTeam/Temp/eai_logs/var/eai/logs'

# 日志目录与产线映射
DIR_LINE_MAPPING = {
    'Flow DP-EPS': 'dpeps1',       # 总成DP
    'FLOW_DP-EPS': 'dpeps1',       # 总成DP
    'Flow DP-SMT': 'dpepp1',       # 电控一线
    'FLOW_DP-SMT': 'dpepp1',       # 电控一线
    'Flow SMT': 'smt2',            # 电控二线
    'FLOW_SMT': 'smt2',            # 电控二线
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
    """从触发数据行提取JSON"""
    match = re.search(r'db trigger get data:(\[.*?\])\s*$', log_line)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            return None
    return None

def parse_kingdee_request(log_line):
    """
    从金蝶请求行提取实际报工的数据
    修复：处理data字段可能是字符串的情况
    """
    match = re.search(r'kingdee request json:\s*(\{.*\})\s*$', log_line)
    if match:
        try:
            req = json.loads(match.group(1))
            data = req.get('data', {})

            # 如果data是字符串，需要再解析一次
            if isinstance(data, str):
                data = json.loads(data)

            model = data.get('Model', {})
            entities = model.get('FEntity', [])

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
        except Exception as e:
            pass
    return None

def parse_kingdee_response(log_line):
    """从金蝶响应行提取SCHB单号"""
    match = re.search(r'kingdee response json:\s*(\{.*\})\s*$', log_line)
    if match:
        try:
            resp = json.loads(match.group(1))
            result = resp.get('Result', {})
            status = result.get('ResponseStatus', {})
            if status.get('IsSuccess'):
                return result.get('Number', '')
        except:
            pass
    return None

def is_flow_complete(log_line):
    """
    判断是否是流程完成行
    修复：使用多种完成标记
    """
    # 多种完成标记
    complete_markers = [
        'run success',
        'start listen db trigger',  # 新版日志格式
        'Oracle数据库执行 end'       # 更新状态完成
    ]
    return any(marker in log_line for marker in complete_markers)

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

def process_log_content(content, line_code):
    """处理日志内容，提取报工成功记录"""
    records = []
    lines = content.split('\n')

    # 状态机变量
    current_trigger_data = None
    current_trigger_time = None
    current_request_data = None
    current_request_time = None
    current_schb_number = None
    waiting_for_complete = False

    for line in lines:
        ts = parse_timestamp(line)

        # 检查触发数据
        trigger_data = parse_trigger_data(line)
        if trigger_data:
            current_trigger_data = trigger_data
            current_trigger_time = ts
            current_request_data = None
            current_schb_number = None
            waiting_for_complete = False
            continue

        # 检查金蝶请求
        request_data = parse_kingdee_request(line)
        if request_data:
            current_request_data = request_data
            current_request_time = ts
            continue

        # 检查金蝶响应（成功的）
        schb = parse_kingdee_response(line)
        if schb:
            current_schb_number = schb
            waiting_for_complete = True
            continue

        # 检查流程完成（有多种标记）
        if waiting_for_complete and current_request_data and current_schb_number:
            if is_flow_complete(line):
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

                # 重置状态
                current_request_data = None
                current_schb_number = None
                waiting_for_complete = False

    return records

def process_log_file(file_path, line_code):
    """处理单个日志文件"""
    try:
        if file_path.endswith('.gz'):
            with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

        return process_log_content(content, line_code)
    except Exception as e:
        print(f"    读取文件失败: {file_path} - {e}")
        return []

def scan_log_directories():
    """扫描日志目录，收集所有日志文件"""
    files_by_line = defaultdict(list)

    for dir_name, line_code in DIR_LINE_MAPPING.items():
        dir_path = os.path.join(LOG_BASE_DIR, dir_name)
        if os.path.exists(dir_path):
            for filename in os.listdir(dir_path):
                if 'MES报工接口' in filename:
                    file_path = os.path.join(dir_path, filename)
                    files_by_line[line_code].append(file_path)

    return files_by_line

def connect_db(line_code):
    """连接数据库"""
    config = DB_CONFIG[line_code]
    conn = cx_Oracle.connect(
        config['user'],
        config['password'],
        config['dsn']
    )
    return conn

def get_existing_schb_packid_pairs(conn):
    """获取已存在的SCHB+PACKID组合"""
    cursor = conn.cursor()
    cursor.execute("SELECT SCHB_NUMBER, PACKID FROM ACC_ERP_REPORT_SUCCESS")
    existing = set((row[0], row[1]) for row in cursor.fetchall())
    cursor.close()
    return existing

def insert_records(conn, records):
    """批量插入记录"""
    if not records:
        return 0

    cursor = conn.cursor()
    inserted = 0

    for record in records:
        try:
            sql = """
            INSERT INTO ACC_ERP_REPORT_SUCCESS (
                WONO, PACKID, PARTNO, CNT, LINE, SCHB_NUMBER, REPORT_TIME, CREATETIME, IS_SUCCESS
            ) VALUES (
                :wono, :packid, :partno, :cnt, :line, :schb_number, :report_time, SYSDATE, 1
            )
            """
            cursor.execute(sql, {
                'wono': record['wono'],
                'packid': record['packid'],
                'partno': record['partno'],
                'cnt': record['cnt'],
                'line': record['line'],
                'schb_number': record['schb_number'],
                'report_time': record['report_time']
            })
            inserted += 1
        except cx_Oracle.IntegrityError:
            pass  # 主键冲突，跳过
        except Exception as e:
            pass  # 其他错误，跳过

    conn.commit()
    cursor.close()
    return inserted

def main():
    """主函数"""
    print("=" * 80)
    print("从本地日志文件重新提取报工成功记录 - 修复版")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 扫描日志文件
    print("\n[步骤1] 扫描日志文件...")
    files_by_line = scan_log_directories()

    for line_code, files in files_by_line.items():
        print(f"  {DB_CONFIG[line_code]['name']}: {len(files)} 个文件")

    # 处理每个产线
    print("\n[步骤2] 提取记录...")
    records_by_line = defaultdict(list)

    for line_code, files in files_by_line.items():
        print(f"\n  [{DB_CONFIG[line_code]['name']}]")
        for i, file_path in enumerate(sorted(files)):
            filename = os.path.basename(file_path)
            records = process_log_file(file_path, line_code)
            if records:
                records_by_line[line_code].extend(records)
                print(f"    {filename}: {len(records)} 条")
            if (i + 1) % 20 == 0:
                print(f"    处理进度: {i+1}/{len(files)}")
        print(f"    小计: {len(records_by_line[line_code])} 条记录")

    # 去重并导入数据库
    print("\n[步骤3] 去重并导入数据库...")
    total_new = 0
    total_dup = 0

    for line_code, records in records_by_line.items():
        if not records:
            continue

        print(f"\n  [{DB_CONFIG[line_code]['name']}]")

        try:
            conn = connect_db(line_code)

            # 获取已存在的记录
            existing = get_existing_schb_packid_pairs(conn)
            print(f"    数据库已有记录: {len(existing)} 条")

            # 去重
            new_records = []
            seen_keys = set()

            for r in records:
                key = (r['schb_number'], r['packid'])
                if key not in existing and key not in seen_keys:
                    new_records.append(r)
                    seen_keys.add(key)

            dup_count = len(records) - len(new_records)
            print(f"    新记录: {len(new_records)}, 重复: {dup_count}")

            # 插入
            if new_records:
                inserted = insert_records(conn, new_records)
                print(f"    成功插入: {inserted} 条")
                total_new += inserted
            total_dup += dup_count

            conn.close()

        except Exception as e:
            print(f"    错误: {e}")

    # 生成报告
    print(f"\n{'=' * 80}")
    print(f"导入完成!")
    print(f"新增记录总数: {total_new}")
    print(f"重复/跳过记录数: {total_dup}")
    print(f"{'=' * 80}")

    # 保存报告
    report = f"""# 报工成功记录重新导入报告

> 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 执行人: 韩大师

## 处理结果

| 项目 | 数值 |
|------|------|
| 新增记录数 | {total_new} |
| 重复/跳过记录数 | {total_dup} |

## 各产线统计

"""
    for line_code, records in records_by_line.items():
        report += f"- {DB_CONFIG[line_code]['name']}: 提取{len(records)}条\n"

    with open('D:/TechTeam/Temp/重新导入报告.md', 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n报告已保存到: D:/TechTeam/Temp/重新导入报告.md")

if __name__ == '__main__':
    main()

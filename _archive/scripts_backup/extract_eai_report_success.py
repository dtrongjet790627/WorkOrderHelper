# -*- coding: utf-8 -*-
"""
从EAI日志提取报工成功记录 - 修复版
用途：解析163服务器上的EAI日志，提取报工成功的记录
作者：韩大师
日期：2026-01-19
修复：从金蝶请求中提取实际报工的PACKID，而不是从触发数据中关联
"""

import re
import json
import gzip
import os
from datetime import datetime
from collections import defaultdict

# 日志文件类型与产线映射
LOG_LINE_MAPPING = {
    'DP-EPS\\IPA MES报工接口': 'dpeps1',      # 总成DP
    'DP-SMT\\MID\\EPP MES报工接口': 'dpepp1', # 电控一线
    'SMT\\MID-Line2MES报工接口': 'smt2',      # 电控二线
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
    """从触发数据行提取JSON（仅用于参考，不再作为关联依据）"""
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
    关键修复：从请求中提取FLot.FNumber（即PACKID）、FMoBillNo（工单号）、
             FMaterialId.FNumber（物料号）、FQuaQty（数量）

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
    """
    从触发数据中查找对应PACKID的产线信息
    因为金蝶请求中不包含LINE字段，需要从触发数据中补充
    """
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
    """
    从日志内容提取报工成功记录 - 修复版

    修复逻辑：
    1. 解析触发数据（仅用于获取LINE信息）
    2. 解析金蝶请求，提取实际报工的PACKID、工单号、物料号、数量
    3. 解析金蝶响应，获取SCHB单号
    4. 当流程成功时，使用请求中的数据（而不是触发数据）作为记录

    返回: list of dict, 每条记录包含:
        - wono: 工单号
        - packid: 包装ID
        - partno: 物料号
        - cnt: 数量
        - line: 产线
        - schb_number: SCHB单号
        - report_time: 报工时间
    """
    records = []

    lines = content.split('\n')

    # 状态机变量
    current_trigger_data = None  # 触发数据，用于补充LINE信息
    current_trigger_time = None  # 触发时间
    current_request_data = None  # 金蝶请求数据（关键：实际报工的内容）
    current_request_time = None  # 请求时间
    current_schb_number = None   # SCHB单号

    for line in lines:
        # 获取当前行的时间戳
        ts = parse_timestamp(line)

        # 检查时间戳，过滤早于开始日期的记录
        if ts and start_date and ts < start_date:
            continue

        # 检查触发数据（用于获取LINE信息）
        trigger_data = parse_trigger_data(line)
        if trigger_data:
            current_trigger_data = trigger_data
            current_trigger_time = ts
            # 重置后续状态
            current_request_data = None
            current_schb_number = None
            continue

        # 检查金蝶请求（关键：提取实际报工的数据）
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
            # 关键修复：使用请求数据而不是触发数据
            for item in current_request_data:
                # 从触发数据中查找LINE信息
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

    return records

def process_log_file(file_path, line_code, start_date=None):
    """处理单个日志文件"""
    records = []

    if file_path.endswith('.gz'):
        with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    else:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

    return extract_records_from_content(content, line_code, start_date)

def get_line_code_from_filename(filename):
    """从文件名判断产线代码"""
    for pattern, code in LOG_LINE_MAPPING.items():
        if pattern in filename:
            return code
    return None

def generate_insert_sql(records, line_code):
    """生成INSERT SQL语句"""
    if not records:
        return []

    sqls = []
    for record in records:
        sql = f"""
INSERT INTO ACC_ERP_REPORT_SUCCESS (
    WONO, PACKID, PARTNO, CNT, LINE, SCHB_NUMBER, REPORT_TIME, CREATETIME, IS_SUCCESS
) VALUES (
    '{record['wono']}',
    '{record['packid']}',
    '{record['partno']}',
    {record['cnt']},
    '{record['line']}',
    '{record['schb_number']}',
    TO_DATE('{record['report_time'].strftime('%Y-%m-%d %H:%M:%S')}', 'YYYY-MM-DD HH24:MI:SS'),
    SYSDATE,
    1
)"""
        sqls.append(sql.strip())

    return sqls

def main():
    """主函数 - 用于测试"""
    print("=" * 80)
    print("EAI日志报工成功记录提取工具 - 修复版")
    print("=" * 80)

    # 测试解析金蝶请求
    test_request = '''[INFO][2026-01-06 22:54:01.655] kingdee request json: {"cmd_name":"Save","form_id":"PRD_MORPT","data":{"Model":{"FDate":"2026-01-06 22:54:01","FEntity":[{"FFinishQty":300,"FLot":{"FNumber":"20260106M2200388"},"FMaterialId":{"FNumber":"D24.204.232"},"FMoBillNo":"MID-225123101","FQuaQty":300}]}}}'''

    request_data = parse_kingdee_request(test_request)
    print(f"\n金蝶请求数据: {request_data}")

    # 测试解析响应
    test_response = '[INFO][2026-01-06 22:54:02.905] kingdee response json: {"Result":{"ResponseStatus":{"IsSuccess":true,"SuccessEntitys":[{"Id":911987,"Number":"SCHB00082561","DIndex":0}]},"Id":911987,"Number":"SCHB00082561"}}'

    schb = parse_kingdee_response(test_response)
    print(f"SCHB单号: {schb}")

    # 测试完整提取
    test_content = """
[INFO][2026-01-06 22:53:56.564] >>>>>>>>>>>>>>>>>>db trigger get data:[{"CNT":"300","LINE":"MID Line2","PACKID":"20260106M2200388","PARTNO":"D24.204.232","WONO":"MID-225123101"},{"CNT":"290","LINE":"MID Line2","PACKID":"20260106M2200387","PARTNO":"D24.204.232","WONO":"MID-225122901"}]
[INFO][2026-01-06 22:54:01.655] kingdee request json: {"cmd_name":"Save","form_id":"PRD_MORPT","data":{"Model":{"FDate":"2026-01-06 22:54:01","FEntity":[{"FFinishQty":300,"FLot":{"FNumber":"20260106M2200388"},"FMaterialId":{"FNumber":"D24.204.232"},"FMoBillNo":"MID-225123101","FQuaQty":300}]}}}
[INFO][2026-01-06 22:54:02.905] kingdee response json: {"Result":{"ResponseStatus":{"IsSuccess":true,"SuccessEntitys":[{"Id":911987,"Number":"SCHB00082561","DIndex":0}]},"Id":911987,"Number":"SCHB00082561"}}
[INFO][2026-01-06 22:54:03.278] >>>>> flow [SMT\\MID-Line2MES报工接口] run success, cost 1698 ms
"""

    records = extract_records_from_content(test_content, 'smt2')
    print(f"\n提取的记录:")
    for r in records:
        print(f"  PACKID={r['packid']}, WONO={r['wono']}, SCHB={r['schb_number']}, CNT={r['cnt']}")

    print("\n注意：之前的bug会错误地提取20260106M2200387，")
    print("      修复后正确提取20260106M2200388（金蝶请求中实际报工的批次）")

if __name__ == '__main__':
    main()

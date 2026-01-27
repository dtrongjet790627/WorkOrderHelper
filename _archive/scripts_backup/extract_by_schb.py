# -*- coding: utf-8 -*-
"""
根据SCHB单号从EAI日志中提取正确的报工记录
作者：韩大师
日期：2026-01-19
"""

import json
import re
import subprocess
import cx_Oracle
from datetime import datetime
from collections import defaultdict

# EAI服务器配置
EAI_SERVER = '172.17.10.163'
EAI_SSH_PORT = 2200
EAI_USER = 'root'
EAI_LOG_DIR = '/var/eai/logs'

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

# 产线映射（根据SCHB文件名前缀判断）
LINE_CODE_MAPPING = {
    'DP-EPS': 'dpeps1',
    'DP-SMT': 'dpepp1',
    'MID-Line2': 'smt2',
    'SMT': 'smt2',
}

def ssh_command(cmd, timeout=300):
    """执行SSH命令"""
    full_cmd = f'ssh -p {EAI_SSH_PORT} {EAI_USER}@{EAI_SERVER} "{cmd}"'
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout, result.stderr, result.returncode

def parse_kingdee_request(json_str):
    """
    从金蝶请求JSON提取实际报工的数据
    """
    try:
        req = json.loads(json_str)
        data = req.get('data', {})
        model = data.get('Model', {})
        entities = model.get('FEntity', [])
        report_time_str = model.get('FDate', '')

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

        return records, report_time_str
    except:
        return None, None

def search_schb_in_logs(schb_number):
    """
    在EAI日志中搜索SCHB单号相关的行
    返回：请求JSON和响应JSON
    """
    # 搜索包含该SCHB单号的响应
    cmd = f'zgrep -h "{schb_number}" {EAI_LOG_DIR}/*MES报工接口*.gz 2>/dev/null; grep -h "{schb_number}" {EAI_LOG_DIR}/*MES报工接口*.log 2>/dev/null'
    stdout, stderr, code = ssh_command(cmd)

    if not stdout.strip():
        return None

    # 解析响应行，获取时间戳
    lines = stdout.strip().split('\n')
    response_line = None
    response_time = None

    for line in lines:
        if 'kingdee response json' in line and schb_number in line:
            response_line = line
            # 提取时间戳
            match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if match:
                response_time = match.group(1)
            break

    if not response_time:
        return None

    # 搜索该时间点前后的请求
    # 时间格式：2026-01-06 22:54:01
    time_prefix = response_time[:16]  # 2026-01-06 22:54

    cmd = f'zgrep -h "kingdee request json.*{time_prefix}" {EAI_LOG_DIR}/*MES报工接口*.gz 2>/dev/null; grep -h "kingdee request json.*{time_prefix}" {EAI_LOG_DIR}/*MES报工接口*.log 2>/dev/null'
    stdout2, _, _ = ssh_command(cmd)

    if not stdout2.strip():
        # 尝试更宽松的搜索
        date_prefix = response_time[:10]  # 2026-01-06
        hour_prefix = response_time[11:13]  # 22

        cmd = f'zgrep -h "kingdee request json.*{date_prefix} {hour_prefix}" {EAI_LOG_DIR}/*MES报工接口*.gz 2>/dev/null; grep -h "kingdee request json.*{date_prefix} {hour_prefix}" {EAI_LOG_DIR}/*MES报工接口*.log 2>/dev/null'
        stdout2, _, _ = ssh_command(cmd)

    return {
        'response_line': response_line,
        'response_time': response_time,
        'request_lines': stdout2.strip().split('\n') if stdout2.strip() else []
    }

def find_matching_request(response_time, request_lines):
    """
    找到与响应时间最接近的请求
    """
    if not request_lines:
        return None

    response_dt = datetime.strptime(response_time, '%Y-%m-%d %H:%M:%S')
    best_match = None
    best_diff = float('inf')

    for line in request_lines:
        match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if match:
            try:
                req_time = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
                diff = abs((response_dt - req_time).total_seconds())
                # 请求应该在响应之前，且时间差小于10秒
                if req_time <= response_dt and diff < 10 and diff < best_diff:
                    best_diff = diff
                    best_match = line
            except:
                continue

    return best_match

def extract_record_for_schb(schb_number, line_code):
    """
    为特定SCHB单号提取正确的记录
    """
    result = search_schb_in_logs(schb_number)
    if not result:
        return None

    # 找到匹配的请求
    request_line = find_matching_request(result['response_time'], result['request_lines'])
    if not request_line:
        return None

    # 提取请求JSON
    match = re.search(r'kingdee request json:\s*(\{.*\})\s*$', request_line)
    if not match:
        return None

    json_str = match.group(1)
    records, report_time_str = parse_kingdee_request(json_str)

    if not records:
        return None

    # 解析报工时间
    try:
        report_time = datetime.strptime(report_time_str, '%Y-%m-%d %H:%M:%S')
    except:
        report_time = datetime.strptime(result['response_time'], '%Y-%m-%d %H:%M:%S')

    # 返回第一条记录（通常一次只报一个批次）
    record = records[0]
    record['schb_number'] = schb_number
    record['report_time'] = report_time
    record['line_code'] = line_code

    return record

def load_backup_schbs(backup_file):
    """加载备份文件中的SCHB单号"""
    with open(backup_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    schbs = set()
    for r in data:
        schbs.add(r['SCHB_NUMBER'])
    return schbs

def connect_db(line_code):
    """连接数据库"""
    config = DB_CONFIG[line_code]
    conn = cx_Oracle.connect(
        config['user'],
        config['password'],
        config['dsn']
    )
    return conn

def insert_record(conn, record):
    """插入单条记录"""
    cursor = conn.cursor()
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
            'line': record.get('line', ''),
            'schb_number': record['schb_number'],
            'report_time': record['report_time']
        })
        conn.commit()
        return True
    except Exception as e:
        print(f"      插入失败: {e}")
        return False
    finally:
        cursor.close()

def main():
    """主函数"""
    print("=" * 80)
    print("根据SCHB单号重新提取报工记录")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 备份文件与产线映射
    backup_files = {
        'dpepp1': 'D:/TechTeam/Temp/backup_dpepp1_20260119_153035.json',
        'smt2': 'D:/TechTeam/Temp/backup_smt2_20260119_153035.json',
        'dpeps1': 'D:/TechTeam/Temp/backup_dpeps1_20260119_153036.json',
    }

    total_processed = 0
    total_inserted = 0
    total_failed = 0

    for line_code, backup_file in backup_files.items():
        print(f"\n[{DB_CONFIG[line_code]['name']}] 处理中...")

        # 加载SCHB单号
        schbs = load_backup_schbs(backup_file)
        print(f"  需要处理的SCHB单号: {len(schbs)} 个")

        # 连接数据库
        conn = connect_db(line_code)

        inserted = 0
        failed = 0

        # 处理每个SCHB单号
        for i, schb in enumerate(sorted(schbs)):
            if (i + 1) % 50 == 0:
                print(f"    进度: {i+1}/{len(schbs)}")

            record = extract_record_for_schb(schb, line_code)
            if record:
                if insert_record(conn, record):
                    inserted += 1
                else:
                    failed += 1
            else:
                failed += 1

        conn.close()

        print(f"  完成: 成功={inserted}, 失败={failed}")
        total_processed += len(schbs)
        total_inserted += inserted
        total_failed += failed

    print(f"\n{'=' * 80}")
    print(f"处理完成!")
    print(f"总处理SCHB数: {total_processed}")
    print(f"成功插入: {total_inserted}")
    print(f"失败: {total_failed}")
    print(f"{'=' * 80}")

if __name__ == '__main__':
    main()

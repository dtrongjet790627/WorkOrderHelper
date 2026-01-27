# -*- coding: utf-8 -*-
"""调试电控一线失败记录提取问题"""

import subprocess
import re
import json
from datetime import datetime
from collections import defaultdict

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
        print(f"SSH命令执行失败: {e}")
        return None

def parse_timestamp(log_line):
    """从日志行提取时间戳"""
    match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', log_line)
    if match:
        return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
    return None

def parse_kingdee_request(log_line):
    """从金蝶请求行提取实际报工的数据"""
    if 'kingdee request json:' not in log_line:
        return None

    # PACKID格式
    packid_match = re.search(r'(\d{8}[A-Z]\d{7})', log_line)
    wono_match = re.search(r'FMoBillNo.*?(EPS\d+|MID-2?\d+|EPP\d+|IPA\d+)', log_line)
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
    """从金蝶响应行提取失败信息"""
    match = re.search(r'kingdee response json:\s*(\{.*\})\s*$', log_line)
    if match:
        try:
            resp = json.loads(match.group(1))
            result = resp.get('Result', {})
            status = result.get('ResponseStatus', {})

            if status.get('IsSuccess'):
                return (True, result.get('Number', ''), None)
            else:
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

# 读取一个测试文件
print("读取电控一线日志文件...")
cmd = 'ssh -p 2200 root@172.17.10.163 "zcat \'/var/eai/logs/FLOW_DP-SMT\\MID\\EPP MES报工接口-2025-12-26T07-01-48.883.log.gz\'"'
content = run_ssh_command(cmd)

if content:
    print(f"日志大小: {len(content)} 字节")

    lines = content.split('\n')
    print(f"总行数: {len(lines)}")

    # 统计各类行
    request_count = 0
    response_fail_count = 0
    flow_failed_count = 0

    # 状态机
    current_request_data = None
    current_error_message = None
    records = []

    for line in lines:
        if 'kingdee request json:' in line:
            request_count += 1
            current_request_data = parse_kingdee_request(line)

        response_result = parse_kingdee_response_fail(line)
        if response_result:
            is_success, _, error_msg = response_result
            if not is_success:
                response_fail_count += 1
                current_error_message = error_msg

        if 'run failed' in line and 'flow' in line:
            flow_failed_count += 1
            if current_request_data and current_error_message:
                for item in current_request_data:
                    records.append({
                        'wono': item['wono'],
                        'packid': item['packid'],
                        'error_message': current_error_message
                    })
            current_request_data = None
            current_error_message = None

    print(f"\n请求行数: {request_count}")
    print(f"失败响应行数: {response_fail_count}")
    print(f"流程失败行数: {flow_failed_count}")
    print(f"提取记录数: {len(records)}")

    # 打印前几条记录
    print("\n前5条记录:")
    for r in records[:5]:
        print(f"  WONO={r['wono']}, PACKID={r['packid']}")
        print(f"  ERROR={r['error_message'][:100]}...")
        print()

    # 去重统计
    groups = defaultdict(list)
    for r in records:
        key = (r['wono'], r['packid'], r['error_message'])
        groups[key].append(r)

    print(f"\n去重后记录数: {len(groups)}")
    print("\n去重后的组合:")
    for key, items in list(groups.items())[:5]:
        print(f"  WONO={key[0]}, PACKID={key[1]}, 重复次数={len(items)}")
        print(f"  ERROR={key[2][:80]}...")
        print()
else:
    print("无法读取日志文件")

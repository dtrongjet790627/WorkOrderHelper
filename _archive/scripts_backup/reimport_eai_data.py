# -*- coding: utf-8 -*-
"""
重新导入EAI报工成功记录
用途：使用修复后的脚本从EAI日志重新提取数据并导入数据库
作者：韩大师
日期：2026-01-19
"""

import os
import sys
import subprocess
import tempfile
import json
import cx_Oracle
from datetime import datetime
from extract_eai_report_success import (
    process_log_file,
    DB_CONFIG,
    LOG_LINE_MAPPING,
    get_line_code_from_filename
)

# EAI服务器配置
EAI_SERVER = '172.17.10.163'
EAI_SSH_PORT = 2200
EAI_USER = 'root'
EAI_LOG_DIR = '/var/eai/logs'

# 本地临时目录
LOCAL_TEMP_DIR = 'D:/TechTeam/Temp/eai_logs'

def ssh_command(cmd):
    """执行SSH命令"""
    full_cmd = f'ssh -p {EAI_SSH_PORT} {EAI_USER}@{EAI_SERVER} "{cmd}"'
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode

def scp_download(remote_path, local_path):
    """从远程下载文件"""
    cmd = f'scp -P {EAI_SSH_PORT} {EAI_USER}@{EAI_SERVER}:"{remote_path}" "{local_path}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0

def list_log_files():
    """列出EAI日志文件"""
    # 列出报工接口相关的日志文件
    patterns = [
        'FLOW_DP-EPS*IPA*MES报工接口*',
        'FLOW_DP-SMT*MID*EPP*MES报工接口*',
        'FLOW_SMT*MID-Line2MES报工接口*',
    ]

    all_files = []
    for pattern in patterns:
        cmd = f'ls -la "{EAI_LOG_DIR}"/"{pattern}" 2>/dev/null || true'
        stdout, stderr, code = ssh_command(cmd)
        if stdout:
            for line in stdout.strip().split('\n'):
                if line and not line.startswith('total'):
                    parts = line.split()
                    if len(parts) >= 9:
                        filename = ' '.join(parts[8:])
                        all_files.append(filename)

    return all_files

def download_log_files():
    """下载日志文件到本地"""
    os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)

    # 使用find命令查找所有报工接口日志
    cmd = f'''find {EAI_LOG_DIR} -name "FLOW*MES报工接口*" -type f 2>/dev/null'''
    stdout, stderr, code = ssh_command(cmd)

    if not stdout.strip():
        print("未找到日志文件")
        return []

    files = stdout.strip().split('\n')
    print(f"找到 {len(files)} 个日志文件")

    downloaded = []
    for remote_path in files:
        filename = os.path.basename(remote_path)
        local_path = os.path.join(LOCAL_TEMP_DIR, filename)

        # 判断产线
        line_code = None
        for pattern, code in LOG_LINE_MAPPING.items():
            if pattern.replace('\\', '') in filename or pattern in filename:
                line_code = code
                break

        if not line_code:
            print(f"  跳过（无法识别产线）: {filename}")
            continue

        print(f"  下载: {filename} -> {line_code}")
        if scp_download(remote_path, local_path):
            downloaded.append((local_path, line_code))
        else:
            print(f"    下载失败: {filename}")

    return downloaded

def connect_db(line_code):
    """连接数据库"""
    config = DB_CONFIG[line_code]
    conn = cx_Oracle.connect(
        config['user'],
        config['password'],
        config['dsn']
    )
    return conn

def get_existing_schb_numbers(conn):
    """获取已存在的SCHB单号"""
    cursor = conn.cursor()
    cursor.execute("SELECT SCHB_NUMBER FROM ACC_ERP_REPORT_SUCCESS")
    existing = set(row[0] for row in cursor.fetchall())
    cursor.close()
    return existing

def insert_records(conn, records):
    """插入记录到数据库"""
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
        except cx_Oracle.IntegrityError as e:
            # 可能是主键冲突，跳过
            pass
        except Exception as e:
            print(f"    插入失败: {record['schb_number']} - {e}")

    conn.commit()
    cursor.close()
    return inserted

def main():
    """主函数"""
    print("=" * 80)
    print("EAI报工成功记录重新导入")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 步骤1：下载日志文件
    print("\n[步骤1] 从EAI服务器下载日志文件...")
    downloaded_files = download_log_files()

    if not downloaded_files:
        print("没有下载到日志文件，退出")
        return

    print(f"\n成功下载 {len(downloaded_files)} 个日志文件")

    # 步骤2：按产线处理日志
    print("\n[步骤2] 解析日志并按产线分组...")
    records_by_line = {
        'dpepp1': [],
        'smt2': [],
        'dpeps1': []
    }

    for local_path, line_code in downloaded_files:
        print(f"  处理: {os.path.basename(local_path)}")
        records = process_log_file(local_path, line_code)
        records_by_line[line_code].extend(records)
        print(f"    提取到 {len(records)} 条记录")

    # 步骤3：去重并导入数据库
    print("\n[步骤3] 去重并导入数据库...")

    total_new = 0
    total_dup = 0

    for line_code, records in records_by_line.items():
        if not records:
            print(f"\n[{DB_CONFIG[line_code]['name']}] 无记录，跳过")
            continue

        print(f"\n[{DB_CONFIG[line_code]['name']}] 处理 {len(records)} 条记录...")

        try:
            conn = connect_db(line_code)

            # 获取已存在的记录
            existing = get_existing_schb_numbers(conn)
            print(f"  数据库已有 {len(existing)} 条记录")

            # 去重
            new_records = []
            seen_keys = set()  # 用于本批次内去重

            for r in records:
                key = (r['schb_number'], r['packid'])
                if r['schb_number'] not in existing and key not in seen_keys:
                    new_records.append(r)
                    seen_keys.add(key)

            dup_count = len(records) - len(new_records)
            print(f"  新记录: {len(new_records)}, 重复: {dup_count}")

            # 插入新记录
            if new_records:
                inserted = insert_records(conn, new_records)
                print(f"  成功插入: {inserted} 条")
                total_new += inserted
                total_dup += dup_count

            conn.close()

        except Exception as e:
            print(f"  错误: {e}")

    # 步骤4：生成报告
    print("\n" + "=" * 80)
    print("导入完成!")
    print(f"新增记录总数: {total_new}")
    print(f"重复记录总数: {total_dup}")
    print("=" * 80)

    # 保存报告
    report_file = 'D:/TechTeam/Temp/重新导入报告.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# EAI报工成功记录重新导入报告\n\n")
        f.write(f"> 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## 统计\n\n")
        f.write(f"| 项目 | 数值 |\n")
        f.write(f"|------|------|\n")
        f.write(f"| 下载日志文件数 | {len(downloaded_files)} |\n")
        f.write(f"| 新增记录数 | {total_new} |\n")
        f.write(f"| 重复记录数 | {total_dup} |\n")

        f.write(f"\n## 各产线统计\n\n")
        for line_code, records in records_by_line.items():
            f.write(f"- {DB_CONFIG[line_code]['name']}: {len(records)} 条提取\n")

    print(f"\n报告已保存到: {report_file}")

if __name__ == '__main__':
    main()

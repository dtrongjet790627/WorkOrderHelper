# -*- coding: utf-8 -*-
"""
从备份文件恢复报工成功记录
作者：韩大师
日期：2026-01-19
说明：由于日志文件已轮转删除，直接从备份恢复数据
      备份中的数据虽然PACKID关联可能有误，但SCHB_NUMBER是准确的
      我们需要分析哪些数据是可以恢复的
"""

import json
import cx_Oracle
from datetime import datetime
from collections import defaultdict

# 数据库连接配置
DB_CONFIG = {
    'dpepp1': {
        'user': 'iplant_dpepp1',
        'password': 'acc',
        'dsn': '172.17.10.165:1521/orcl.ecdag.com',
        'name': '电控一线',
        'backup_file': 'D:/TechTeam/Temp/backup_dpepp1_20260119_153035.json'
    },
    'smt2': {
        'user': 'iplant_smt2',
        'password': 'acc',
        'dsn': '172.17.10.165:1521/orcl.ecdag.com',
        'name': '电控二线',
        'backup_file': 'D:/TechTeam/Temp/backup_smt2_20260119_153035.json'
    },
    'dpeps1': {
        'user': 'iplant_dpeps1',
        'password': 'acc',
        'dsn': '172.17.10.165:1521/orcl.ecdag.com',
        'name': '总成DP',
        'backup_file': 'D:/TechTeam/Temp/backup_dpeps1_20260119_153036.json'
    }
}

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

def load_backup(backup_file):
    """加载备份文件"""
    with open(backup_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_next_id(conn):
    """获取下一个ID"""
    cursor = conn.cursor()
    cursor.execute('SELECT NVL(MAX(ID), 0) + 1 FROM ACC_ERP_REPORT_SUCCESS')
    next_id = cursor.fetchone()[0]
    cursor.close()
    return next_id

def insert_records_batch(conn, records):
    """批量插入记录"""
    if not records:
        return 0

    cursor = conn.cursor()
    inserted = 0

    # 获取起始ID
    next_id = get_next_id(conn)

    for record in records:
        try:
            # 解析报工时间
            report_time = datetime.strptime(record['REPORT_TIME'], '%Y-%m-%d %H:%M:%S')

            sql = """
            INSERT INTO ACC_ERP_REPORT_SUCCESS (
                ID, WONO, PACKID, PARTNO, CNT, LINE, SCHB_NUMBER, REPORT_TIME, CREATETIME, IS_SUCCESS
            ) VALUES (
                :id, :wono, :packid, :partno, :cnt, :line, :schb_number, :report_time, SYSDATE, 1
            )
            """
            cursor.execute(sql, {
                'id': next_id,
                'wono': record['WONO'],
                'packid': record['PACKID'],
                'partno': record['PARTNO'],
                'cnt': record['CNT'],
                'line': record['LINE'],
                'schb_number': record['SCHB_NUMBER'],
                'report_time': report_time
            })
            next_id += 1
            inserted += 1
        except Exception as e:
            print(f"    插入失败: {record['SCHB_NUMBER']} - {e}")

    conn.commit()
    cursor.close()
    return inserted

def insert_record(conn, record):
    """插入单条记录（兼容旧接口）"""
    return insert_records_batch(conn, [record]) > 0

def main():
    """主函数"""
    print("=" * 80)
    print("从备份文件恢复报工成功记录")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print("\n注意：由于EAI日志已轮转删除，无法从日志重新提取正确的PACKID关联。")
    print("本脚本将从备份文件恢复数据（包含原始的PACKID关联）。")
    print("这些数据的PACKID可能存在关联错误，但SCHB_NUMBER是准确的。\n")

    total_restored = 0
    total_skipped = 0

    for line_code, config in DB_CONFIG.items():
        print(f"\n[{config['name']}]")

        try:
            # 加载备份
            backup_data = load_backup(config['backup_file'])
            print(f"  备份文件: {len(backup_data)} 条记录")

            # 连接数据库
            conn = connect_db(line_code)

            # 获取已存在的SCHB
            existing = get_existing_schb_numbers(conn)
            print(f"  数据库已有: {len(existing)} 条记录")

            # 找出需要恢复的记录（按SCHB去重）
            to_restore = []
            seen_schbs = set()

            for record in backup_data:
                schb = record['SCHB_NUMBER']
                if schb not in existing and schb not in seen_schbs:
                    to_restore.append(record)
                    seen_schbs.add(schb)

            print(f"  需要恢复: {len(to_restore)} 条（按SCHB去重）")

            # 批量插入记录
            restored = insert_records_batch(conn, to_restore)
            print(f"  成功恢复: {restored} 条")
            total_restored += restored
            total_skipped += len(backup_data) - len(to_restore)

            conn.close()

        except Exception as e:
            print(f"  错误: {e}")

    # 汇总
    print(f"\n{'=' * 80}")
    print(f"恢复完成!")
    print(f"总恢复记录数: {total_restored}")
    print(f"跳过（已存在）: {total_skipped}")
    print(f"{'=' * 80}")

    # 更新报告
    report = f"""# 数据校验修复报告

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 执行人: 韩大师

---

## 任务背景

之前通过脚本从EAI日志提取报工成功记录插入到ACC_ERP_REPORT_SUCCESS表中，但脚本逻辑有bug，导致PACKID关联错误。

## 执行结果

### 1. 错误数据删除

| 产线 | 删除记录数 |
|------|-----------|
| 电控一线 | 738 |
| 电控二线 | 702 |
| 总成DP | 955 |
| **总计** | **2395** |

### 2. 数据恢复

由于EAI服务器上的日志文件已经轮转删除（2025年9月-12月的日志不存在），无法从日志重新提取正确的PACKID关联。

最终决定从备份文件恢复数据：

| 项目 | 数值 |
|------|------|
| 恢复记录数 | {total_restored} |
| 跳过（已存在） | {total_skipped} |

### 3. 脚本修复

已修复 `D:/TechTeam/Scripts/extract_eai_report_success.py` 脚本：

**修复内容**：
- 从金蝶请求JSON中提取实际报工的PACKID（FLot.FNumber字段）
- 而不是从触发数据中关联PACKID
- 确保PACKID与SCHB单号的正确对应

**修复后的逻辑**：
1. 解析触发数据（仅用于获取LINE信息）
2. 解析金蝶请求，提取实际报工的数据（关键修复点）
3. 解析金蝶响应，获取SCHB单号
4. 当流程成功时，使用请求中的数据作为记录

### 4. 遗留问题

恢复的数据中，PACKID关联可能存在以下问题：
- 部分记录的PACKID可能与实际报工的批次不一致
- 这是由于原始脚本bug导致的数据问题
- SCHB_NUMBER是准确的，可以作为与金蝶系统对账的依据

建议：如需精确的PACKID信息，可以通过SCHB单号与金蝶系统进行比对。

---

## 备份文件位置

| 产线 | 备份文件 |
|------|----------|
| 电控一线 | D:/TechTeam/Temp/backup_dpepp1_20260119_153035.json |
| 电控二线 | D:/TechTeam/Temp/backup_smt2_20260119_153035.json |
| 总成DP | D:/TechTeam/Temp/backup_dpeps1_20260119_153036.json |
"""

    with open('D:/TechTeam/Temp/数据校验修复报告.md', 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n报告已保存到: D:/TechTeam/Temp/数据校验修复报告.md")

if __name__ == '__main__':
    main()

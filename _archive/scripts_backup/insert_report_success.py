# -*- coding: utf-8 -*-
"""
插入报工成功记录到ACC_ERP_REPORT_SUCCESS表
作者：韩大师
日期：2026-01-19
"""

import cx_Oracle
import json
from datetime import datetime

# 加载提取的数据
DATA_FILE = 'D:/TechTeam/Scripts/eai_report_success_records.json'

# 数据库配置
DB_CONFIGS = {
    'dpeps1': {
        'user': 'iplant_dpeps1',
        'password': 'acc',
        'dsn': '172.17.10.165:1521/orcl.ecdag.com',
        'name': '总成DP'
    },
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
}

def insert_records(line_code, records, dry_run=False):
    """插入记录到数据库"""
    config = DB_CONFIGS.get(line_code)
    if not config:
        print(f"未知产线: {line_code}")
        return 0

    conn = cx_Oracle.connect(f"{config['user']}/{config['password']}@{config['dsn']}")
    cursor = conn.cursor()

    try:
        # 获取已存在的PACKID
        cursor.execute('SELECT PACKID FROM ACC_ERP_REPORT_SUCCESS')
        existing_packids = set(row[0] for row in cursor.fetchall())

        # 获取当前最大ID
        cursor.execute('SELECT NVL(MAX(ID), 0) FROM ACC_ERP_REPORT_SUCCESS')
        max_id = cursor.fetchone()[0]
        print(f"{config['name']}: 当前最大ID = {max_id}")

        # 过滤出新记录
        new_records = [r for r in records if r['packid'] not in existing_packids]

        if not new_records:
            print(f"{config['name']}: 没有新记录需要插入")
            return 0

        print(f"{config['name']}: 准备插入 {len(new_records)} 条新记录")

        if dry_run:
            print("  [DRY RUN] 跳过实际插入")
            return len(new_records)

        # 批量插入（包含ID字段）
        insert_sql = """
        INSERT INTO ACC_ERP_REPORT_SUCCESS (
            ID, WONO, PACKID, PARTNO, CNT, LINE, SCHB_NUMBER, REPORT_TIME, CREATETIME, IS_SUCCESS
        ) VALUES (
            :id, :wono, :packid, :partno, :cnt, :line, :schb_number,
            TO_DATE(:report_time, 'YYYY-MM-DD HH24:MI:SS'),
            SYSDATE, 1
        )
        """

        batch_size = 100
        inserted = 0
        current_id = max_id

        for i in range(0, len(new_records), batch_size):
            batch = new_records[i:i+batch_size]
            params = []
            for r in batch:
                current_id += 1
                params.append({
                    'id': current_id,
                    'wono': r['wono'],
                    'packid': r['packid'],
                    'partno': r['partno'],
                    'cnt': r['cnt'],
                    'line': r['line'],
                    'schb_number': r['schb_number'],
                    'report_time': r['report_time']
                })

            cursor.executemany(insert_sql, params)
            inserted += len(batch)
            print(f"  已插入 {inserted}/{len(new_records)} 条...")

        conn.commit()
        print(f"{config['name']}: 成功插入 {inserted} 条记录")
        return inserted

    except Exception as e:
        conn.rollback()
        print(f"{config['name']}: 插入失败 - {e}")
        raise

    finally:
        cursor.close()
        conn.close()


def main(dry_run=False):
    """主函数"""
    print("=" * 60)
    print("EAI报工成功记录插入工具")
    print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 加载数据
    with open(DATA_FILE, 'r') as f:
        all_records = json.load(f)

    print(f"\n加载数据文件: {DATA_FILE}")
    for line_code, records in all_records.items():
        print(f"  {line_code}: {len(records)} 条")

    if dry_run:
        print("\n[DRY RUN 模式] - 不会实际修改数据库")

    print("\n" + "-" * 60)

    total_inserted = 0

    for line_code, records in all_records.items():
        if records:
            try:
                count = insert_records(line_code, records, dry_run)
                total_inserted += count
            except Exception as e:
                print(f"处理 {line_code} 时出错: {e}")

    print("\n" + "=" * 60)
    print(f"完成! 共插入 {total_inserted} 条记录")
    print("=" * 60)


if __name__ == '__main__':
    import sys
    dry_run = '--dry-run' in sys.argv
    main(dry_run)

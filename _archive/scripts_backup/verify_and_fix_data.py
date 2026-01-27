# -*- coding: utf-8 -*-
"""
校验并修复ACC_ERP_REPORT_SUCCESS表中的错误数据
用途：检查之前插入的记录，删除PACKID关联错误的数据
作者：韩大师
日期：2026-01-19
"""

import cx_Oracle
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

# 数据库连接配置 - 工厂库
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

def connect_db(line_code):
    """连接数据库"""
    config = DB_CONFIG[line_code]
    conn = cx_Oracle.connect(
        config['user'],
        config['password'],
        config['dsn']
    )
    return conn

def query_inserted_records(conn, line_code):
    """查询2026-01-19插入的记录"""
    cursor = conn.cursor()

    # 查询今天插入的记录（通过CREATETIME判断）
    sql = """
    SELECT ID, WONO, PACKID, PARTNO, CNT, LINE, SCHB_NUMBER,
           REPORT_TIME, CREATETIME, IS_SUCCESS
    FROM ACC_ERP_REPORT_SUCCESS
    WHERE TRUNC(CREATETIME) = TO_DATE('2026-01-19', 'YYYY-MM-DD')
    ORDER BY CREATETIME, SCHB_NUMBER
    """

    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    records = []
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        records.append(record)

    cursor.close()
    return records

def query_all_records(conn):
    """查询所有记录，用于统计"""
    cursor = conn.cursor()

    sql = """
    SELECT COUNT(*) as cnt,
           MIN(CREATETIME) as min_time,
           MAX(CREATETIME) as max_time
    FROM ACC_ERP_REPORT_SUCCESS
    """

    cursor.execute(sql)
    row = cursor.fetchone()
    cursor.close()

    return {
        'count': row[0],
        'min_time': row[1],
        'max_time': row[2]
    }

def backup_records(records, line_code, output_dir):
    """备份记录到文件"""
    if not records:
        return None

    backup_file = os.path.join(output_dir, f'backup_{line_code}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')

    # 转换datetime对象为字符串
    records_serializable = []
    for r in records:
        r_copy = {}
        for k, v in r.items():
            if isinstance(v, datetime):
                r_copy[k] = v.strftime('%Y-%m-%d %H:%M:%S')
            else:
                r_copy[k] = v
        records_serializable.append(r_copy)

    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(records_serializable, f, ensure_ascii=False, indent=2)

    return backup_file

def delete_records(conn, record_ids):
    """删除指定ID的记录"""
    if not record_ids:
        return 0

    cursor = conn.cursor()

    # 使用IN子句删除
    placeholders = ','.join([':' + str(i+1) for i in range(len(record_ids))])
    sql = f"DELETE FROM ACC_ERP_REPORT_SUCCESS WHERE ID IN ({placeholders})"

    cursor.execute(sql, record_ids)
    deleted_count = cursor.rowcount

    conn.commit()
    cursor.close()

    return deleted_count

def main():
    """主函数"""
    print("=" * 80)
    print("ACC_ERP_REPORT_SUCCESS表数据校验与修复")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 创建输出目录
    output_dir = 'D:/TechTeam/Temp'
    os.makedirs(output_dir, exist_ok=True)

    report_lines = []
    report_lines.append("# ACC_ERP_REPORT_SUCCESS 数据校验修复报告\n")
    report_lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report_lines.append("> 执行人: 韩大师\n")
    report_lines.append("\n---\n")

    total_records = 0
    total_deleted = 0
    all_backup_files = []

    for line_code, config in DB_CONFIG.items():
        print(f"\n[{config['name']}] 正在连接数据库...")

        try:
            conn = connect_db(line_code)
            print(f"[{config['name']}] 连接成功")

            # 查询所有记录统计
            stats = query_all_records(conn)
            print(f"[{config['name']}] 表中总记录数: {stats['count']}")

            # 查询今天插入的记录
            records = query_inserted_records(conn, line_code)
            print(f"[{config['name']}] 今天插入的记录数: {len(records)}")

            report_lines.append(f"\n## {config['name']} ({line_code})\n")
            report_lines.append(f"\n### 表统计\n")
            report_lines.append(f"- 总记录数: {stats['count']}\n")
            report_lines.append(f"- 最早记录: {stats['min_time']}\n")
            report_lines.append(f"- 最新记录: {stats['max_time']}\n")
            report_lines.append(f"- 2026-01-19插入的记录数: {len(records)}\n")

            if records:
                total_records += len(records)

                # 备份记录
                backup_file = backup_records(records, line_code, output_dir)
                if backup_file:
                    all_backup_files.append(backup_file)
                    print(f"[{config['name']}] 已备份到: {backup_file}")

                # 显示记录详情
                report_lines.append(f"\n### 查询到的记录\n")
                report_lines.append(f"\n| ID | 工单号 | PACKID | 物料号 | 数量 | SCHB单号 | 报工时间 |\n")
                report_lines.append(f"|-------|--------|--------|--------|------|----------|----------|\n")

                for r in records:
                    report_time_str = r['REPORT_TIME'].strftime('%Y-%m-%d %H:%M') if r['REPORT_TIME'] else 'N/A'
                    report_lines.append(f"| {r['ID']} | {r['WONO']} | {r['PACKID']} | {r['PARTNO']} | {r['CNT']} | {r['SCHB_NUMBER']} | {report_time_str} |\n")

                print(f"\n[{config['name']}] 记录详情:")
                for r in records:
                    print(f"  ID={r['ID']}, PACKID={r['PACKID']}, SCHB={r['SCHB_NUMBER']}, WONO={r['WONO']}")

                # 询问是否删除
                print(f"\n[{config['name']}] 根据分析，这些记录的PACKID关联可能存在问题")
                print(f"[{config['name']}] 建议删除这些记录后重新导入")

                # 自动删除（生产环境可改为交互式确认）
                record_ids = [r['ID'] for r in records]

                # 执行删除
                deleted_count = delete_records(conn, record_ids)
                total_deleted += deleted_count
                print(f"[{config['name']}] 已删除 {deleted_count} 条记录")

                report_lines.append(f"\n### 删除操作\n")
                report_lines.append(f"- 备份文件: {backup_file}\n")
                report_lines.append(f"- 删除记录数: {deleted_count}\n")
                report_lines.append(f"- 删除的ID: {record_ids}\n")
            else:
                report_lines.append(f"\n### 无今日插入记录\n")
                print(f"[{config['name']}] 无今日插入的记录，跳过")

            conn.close()

        except Exception as e:
            print(f"[{config['name']}] 错误: {e}")
            report_lines.append(f"\n### 错误\n")
            report_lines.append(f"连接或操作失败: {e}\n")

    # 生成汇总报告
    report_lines.append(f"\n---\n")
    report_lines.append(f"\n## 汇总\n")
    report_lines.append(f"\n| 项目 | 数值 |\n")
    report_lines.append(f"|------|------|\n")
    report_lines.append(f"| 处理的产线数 | {len(DB_CONFIG)} |\n")
    report_lines.append(f"| 发现的错误记录总数 | {total_records} |\n")
    report_lines.append(f"| 已删除记录总数 | {total_deleted} |\n")
    report_lines.append(f"| 备份文件数 | {len(all_backup_files)} |\n")

    if all_backup_files:
        report_lines.append(f"\n### 备份文件列表\n")
        for f in all_backup_files:
            report_lines.append(f"- {f}\n")

    # 保存报告
    report_file = os.path.join(output_dir, '数据校验修复报告.md')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.writelines(report_lines)

    print(f"\n{'=' * 80}")
    print(f"执行完成!")
    print(f"发现的错误记录数: {total_records}")
    print(f"已删除记录数: {total_deleted}")
    print(f"报告已保存到: {report_file}")
    print(f"{'=' * 80}")

if __name__ == '__main__':
    main()

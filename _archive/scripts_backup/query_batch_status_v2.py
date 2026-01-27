# -*- coding: utf-8 -*-
"""
查询批次状态脚本 V2 - 先检查表结构
工单号: MID-225120801
批次号: 20251212M2200275, 20251213M2200276, 20251213M2200277, 20251213M2200278
数据库: 电控二线工厂库 (iplant_smt2)
"""
import cx_Oracle
import os

# 设置Oracle客户端编码
os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.UTF8'

# 数据库连接信息
DB_CONFIG = {
    'user': 'iplant_smt2',
    'password': 'acc',
    'dsn': '172.17.10.165:1521/orcl.ecdag.com'
}

# 批次号列表
PACK_IDS = ['20251212M2200275', '20251213M2200276', '20251213M2200277', '20251213M2200278']
WONO = 'MID-225120801'

def format_result(cursor, title):
    """格式化输出查询结果"""
    print("\n" + "=" * 80)
    print(f"[{title}]")
    print("=" * 80)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    if not rows:
        print("(无数据)")
        return 0

    # 计算列宽
    col_widths = []
    for i, col in enumerate(columns):
        max_width = len(str(col))
        for row in rows:
            val_len = len(str(row[i]) if row[i] is not None else 'NULL')
            max_width = max(max_width, val_len)
        col_widths.append(min(max_width, 50))  # 限制最大宽度

    # 打印表头
    header = " | ".join(str(col).ljust(col_widths[i]) for i, col in enumerate(columns))
    print(header)
    print("-" * len(header))

    # 打印数据
    for row in rows:
        row_str = " | ".join(
            str(val if val is not None else 'NULL').ljust(col_widths[i])[:col_widths[i]]
            for i, val in enumerate(row)
        )
        print(row_str)

    print(f"\nTotal: {len(rows)} rows")
    return len(rows)

def describe_table(cursor, table_name):
    """获取表结构"""
    sql = f"""
    SELECT column_name, data_type, data_length
    FROM user_tab_columns
    WHERE table_name = UPPER('{table_name}')
    ORDER BY column_id
    """
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        if rows:
            print(f"\nTable {table_name} columns:")
            for row in rows:
                print(f"  - {row[0]} ({row[1]})")
            return [r[0] for r in rows]
        else:
            print(f"\nTable {table_name} not found")
            return []
    except Exception as e:
        print(f"Error describing {table_name}: {e}")
        return []

def main():
    print("=" * 80)
    print("ACC Database Batch Status Query")
    print(f"Work Order: {WONO}")
    print(f"Batch IDs: {', '.join(PACK_IDS)}")
    print(f"Database: iplant_smt2@172.17.10.165")
    print("=" * 80)

    try:
        conn = cx_Oracle.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("\nDatabase connected!")

        pack_ids_str = ",".join(f"'{p}'" for p in PACK_IDS)

        # 先获取pack_info表结构
        print("\n--- Checking table structures ---")
        pack_info_cols = describe_table(cursor, 'pack_info')
        pack_history_cols = describe_table(cursor, 'pack_history')

        # 1. 查询 pack_info 表 - 包装主表
        if pack_info_cols:
            # 根据实际字段查询
            sql1 = f"""
            SELECT *
            FROM pack_info
            WHERE packid IN ({pack_ids_str})
            ORDER BY packid
            """
            cursor.execute(sql1)
            format_result(cursor, "pack_info - Package Main Table")

        # 2. 查询 pack_history 表 - 包装历史
        if pack_history_cols:
            sql2 = f"""
            SELECT *
            FROM pack_history
            WHERE packid IN ({pack_ids_str})
            AND ROWNUM <= 20
            ORDER BY packid
            """
            cursor.execute(sql2)
            format_result(cursor, "pack_history - Package History (first 20)")

        # 3. 查询 acc_wo_workorder_detail 表 - 工单明细
        print("\n--- Checking acc_wo_workorder_detail ---")
        wo_cols = describe_table(cursor, 'acc_wo_workorder_detail')
        if wo_cols:
            sql3 = f"""
            SELECT *
            FROM acc_wo_workorder_detail
            WHERE wono = '{WONO}' AND status = 2
            AND ROWNUM <= 10
            """
            cursor.execute(sql3)
            format_result(cursor, "acc_wo_workorder_detail (status=2, first 10)")

        # 4. 查找报工相关表
        print("\n--- Finding report related tables ---")
        sql_tables = """
        SELECT table_name FROM user_tables
        WHERE UPPER(table_name) LIKE '%REPORT%'
           OR UPPER(table_name) LIKE '%ERP%'
           OR UPPER(table_name) LIKE '%SUCCESS%'
        ORDER BY table_name
        """
        cursor.execute(sql_tables)
        tables = cursor.fetchall()
        print("\nReport related tables found:")
        for t in tables:
            print(f"  - {t[0]}")

        # 尝试查询报工成功表（可能有不同的表名）
        report_tables = [
            'ACC_ERP_REPORT_SUCCESS',
            'ERP_REPORT_SUCCESS',
            'ACC_REPORT_SUCCESS',
            'EPR_REPORT_WORK_HISTORY',
            'ERP_REPORT_WORK_HISTORY',
            'ACC_ERP_REPORT_HISTORY'
        ]

        for table in report_tables:
            try:
                sql = f"SELECT * FROM {table} WHERE ROWNUM = 1"
                cursor.execute(sql)
                print(f"\nTable {table} exists!")
                cols = describe_table(cursor, table)

                # 尝试查询
                sql_query = f"""
                SELECT * FROM {table}
                WHERE packid IN ({pack_ids_str})
                """
                cursor.execute(sql_query)
                format_result(cursor, f"{table}")
            except cx_Oracle.DatabaseError:
                pass  # 表不存在

        # 5. 查询包装状态详情
        print("\n--- Pack Status Details ---")
        sql_pack_status = f"""
        SELECT p.packid, p.status, p.currquantity, p.createtime,
               (SELECT COUNT(*) FROM pack_history h WHERE h.packid = p.packid) as history_count
        FROM pack_info p
        WHERE p.packid IN ({pack_ids_str})
        ORDER BY p.packid
        """
        try:
            cursor.execute(sql_pack_status)
            format_result(cursor, "Pack Status Summary")
        except Exception as e:
            print(f"Query error: {e}")

        cursor.close()
        conn.close()
        print("\n\nQuery completed, database connection closed.")

    except cx_Oracle.DatabaseError as e:
        error, = e.args
        print(f"\nDatabase Error: {error.message}")
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

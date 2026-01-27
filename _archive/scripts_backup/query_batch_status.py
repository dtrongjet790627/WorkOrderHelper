# -*- coding: utf-8 -*-
"""
查询批次状态脚本
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
    print(f"【{title}】")
    print("=" * 80)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    if not rows:
        print("(无数据)")
        return

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

    print(f"\n共 {len(rows)} 条记录")

def main():
    print("=" * 80)
    print("ACC数据库批次状态查询")
    print(f"工单号: {WONO}")
    print(f"批次号: {', '.join(PACK_IDS)}")
    print(f"数据库: iplant_smt2@172.17.10.165 (电控二线工厂库)")
    print("=" * 80)

    try:
        conn = cx_Oracle.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("\n数据库连接成功!")

        pack_ids_str = ",".join(f"'{p}'" for p in PACK_IDS)

        # 1. 查询 pack_info 表 - 包装主表
        sql1 = f"""
        SELECT packid, status, currquantity, createtime, wono
        FROM pack_info
        WHERE packid IN ({pack_ids_str})
        ORDER BY packid
        """
        cursor.execute(sql1)
        format_result(cursor, "pack_info - 包装主表")

        # 2. 查询 pack_history 表 - 包装历史
        sql2 = f"""
        SELECT packid, unitsn, line, packtime
        FROM pack_history
        WHERE packid IN ({pack_ids_str})
        ORDER BY packid, packtime
        """
        cursor.execute(sql2)
        format_result(cursor, "pack_history - 包装历史")

        # 3. 查询 acc_wo_workorder_detail 表 - 工单明细(状态=2的前10条)
        sql3 = f"""
        SELECT wono, unitsn, status, line
        FROM acc_wo_workorder_detail
        WHERE wono = '{WONO}' AND status = 2
        AND ROWNUM <= 10
        """
        cursor.execute(sql3)
        format_result(cursor, "acc_wo_workorder_detail - 工单明细(status=2)")

        # 4. 查询 ACC_ERP_REPORT_SUCCESS 表 - 报工成功记录
        sql4 = f"""
        SELECT packid, schb_number, cnt, report_time, is_success
        FROM ACC_ERP_REPORT_SUCCESS
        WHERE packid IN ({pack_ids_str})
        ORDER BY packid
        """
        try:
            cursor.execute(sql4)
            format_result(cursor, "ACC_ERP_REPORT_SUCCESS - 报工成功记录")
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            if 'ORA-00942' in str(error.message):
                print(f"\n【ACC_ERP_REPORT_SUCCESS - 报工成功记录】")
                print("表不存在或无权限访问")
            else:
                raise

        # 5. 查询 epr_report_work_history 表 - 报工历史
        sql5 = f"""
        SELECT packid, wono, report_time, qty
        FROM epr_report_work_history
        WHERE packid IN ({pack_ids_str})
        ORDER BY packid
        """
        try:
            cursor.execute(sql5)
            format_result(cursor, "epr_report_work_history - 报工历史")
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            if 'ORA-00942' in str(error.message):
                print(f"\n【epr_report_work_history - 报工历史】")
                print("表不存在或无权限访问")
            else:
                raise

        # 额外查询：检查这些批次的报工记录
        print("\n" + "=" * 80)
        print("【额外查询 - 检查报工相关表】")
        print("=" * 80)

        # 尝试查找报工相关的表
        sql_find_tables = """
        SELECT table_name FROM user_tables
        WHERE UPPER(table_name) LIKE '%REPORT%' OR UPPER(table_name) LIKE '%ERP%'
        ORDER BY table_name
        """
        cursor.execute(sql_find_tables)
        tables = cursor.fetchall()
        print("\n报工相关表列表:")
        for t in tables:
            print(f"  - {t[0]}")

        cursor.close()
        conn.close()
        print("\n\n查询完成，数据库连接已关闭。")

    except cx_Oracle.DatabaseError as e:
        error, = e.args
        print(f"\n数据库错误: {error.message}")
    except Exception as e:
        print(f"\n错误: {str(e)}")

if __name__ == '__main__':
    main()

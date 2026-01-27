# -*- coding: utf-8 -*-
"""操作日志记录工具模块

提供三类操作日志记录功能:
- WOA_WORKORDER_OP: 工单操作日志
- WOA_PACKING_OP: 打包操作日志
- WOA_HULU_SYNC: HULU同步日志

日志表存储在iplant_web用户下(172.17.10.165)
"""

import cx_Oracle
from config.database import DB_CONFIG


def get_log_connection():
    """获取日志数据库连接(iplant_web)

    Returns:
        cx_Oracle.Connection: 数据库连接对象
    """
    dsn = cx_Oracle.makedsn(DB_CONFIG['host'], DB_CONFIG['port'], service_name=DB_CONFIG['service_name'])
    return cx_Oracle.connect(user='iplant_web', password='iplant', dsn=dsn)


def log_workorder_op(unitsn, linename, wono, partno, product_status, operator, result, remark):
    """记录工单操作日志

    Args:
        unitsn: 主码(产品序列号)
        linename: 产线名称
        wono: 工单号
        partno: 型号
        product_status: 产品状态(1=未完成, 2=完成)
        operator: 操作人
        result: 操作结果('SUCCESS'/'FAIL')
        remark: 备注信息
    """
    try:
        conn = get_log_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO WOA_WORKORDER_OP
            (UNITSN, LINENAME, WONO, PARTNO, PRODUCT_STATUS, OP_TIME, OPERATOR, RESULT, REMARK)
            VALUES
            (:unitsn, :linename, :wono, :partno, :product_status, SYSDATE, :operator, :result, :remark)
        """, {
            'unitsn': unitsn[:100] if unitsn else None,
            'linename': linename[:20] if linename else None,
            'wono': wono[:50] if wono else None,
            'partno': partno[:50] if partno else None,
            'product_status': product_status,
            'operator': operator[:50] if operator else None,
            'result': result[:10] if result else None,
            'remark': remark[:200] if remark else None
        })

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        # 日志记录失败不影响主业务
        print(f"[LOG ERROR] log_workorder_op failed: {e}")


def log_packing_op(unitsn, linename, wono, partno, packid, operator, result='SUCCESS', remark=None):
    """记录打包操作日志（每个unitsn一条记录）

    Args:
        unitsn: 主码(产品序列号)
        linename: 产线名称
        wono: 工单号
        partno: 型号
        packid: 批次号
        operator: 操作人
        result: 操作结果('SUCCESS'/'FAIL')，默认SUCCESS
        remark: 备注信息
    """
    try:
        conn = get_log_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO WOA_PACKING_OP
            (UNITSN, LINENAME, WONO, PARTNO, PACKID, OP_TIME, OPERATOR, RESULT, REMARK)
            VALUES
            (:unitsn, :linename, :wono, :partno, :packid, SYSDATE, :operator, :result, :remark)
        """, {
            'unitsn': unitsn[:100] if unitsn else None,
            'linename': linename[:20] if linename else None,
            'wono': wono[:50] if wono else None,
            'partno': partno[:50] if partno else None,
            'packid': packid[:50] if packid else None,
            'operator': operator[:50] if operator else None,
            'result': result[:10] if result else 'SUCCESS',
            'remark': remark[:200] if remark else None
        })

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        # 日志记录失败不影响主业务
        print(f"[LOG ERROR] log_packing_op failed: {e}")


def log_hulu_sync(unitsn, linename, wono, partno, sync_type, acc_count, hulu_count, operator, result, remark):
    """记录HULU同步日志

    Args:
        unitsn: 主码(产品序列号)
        linename: 产线名称
        wono: 工单号
        partno: 型号
        sync_type: 同步类型('UPDATE'/'INSERT')
        acc_count: ACC数量
        hulu_count: HULU数量
        operator: 操作人
        result: 操作结果('SUCCESS'/'FAIL')
        remark: 备注信息
    """
    try:
        conn = get_log_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO WOA_HULU_SYNC
            (UNITSN, LINENAME, WONO, PARTNO, SYNC_TYPE, ACC_COUNT, HULU_COUNT, OP_TIME, OPERATOR, RESULT, REMARK)
            VALUES
            (:unitsn, :linename, :wono, :partno, :sync_type, :acc_count, :hulu_count, SYSDATE, :operator, :result, :remark)
        """, {
            'unitsn': unitsn[:100] if unitsn else None,
            'linename': linename[:20] if linename else None,
            'wono': wono[:50] if wono else None,
            'partno': partno[:50] if partno else None,
            'sync_type': sync_type[:20] if sync_type else None,
            'acc_count': acc_count,
            'hulu_count': hulu_count,
            'operator': operator[:50] if operator else None,
            'result': result[:10] if result else None,
            'remark': remark[:200] if remark else None
        })

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        # 日志记录失败不影响主业务
        print(f"[LOG ERROR] log_hulu_sync failed: {e}")


def log_hulu_sync_batch(sync_records, operator, wono, partno, linename):
    """批量记录HULU同步日志(每条产品单独记录)

    Args:
        sync_records: 同步记录列表 [{'unitsn': xx, 'sync_type': 'UPDATE'/'INSERT', 'result': 'SUCCESS'/'FAIL'}]
        operator: 操作人
        wono: 工单号
        partno: 型号
        linename: 产线名称
    """
    if not sync_records:
        return

    try:
        conn = get_log_connection()
        cursor = conn.cursor()

        for record in sync_records:
            try:
                cursor.execute("""
                    INSERT INTO WOA_HULU_SYNC
                    (UNITSN, LINENAME, WONO, PARTNO, SYNC_TYPE, ACC_COUNT, HULU_COUNT, OP_TIME, OPERATOR, RESULT, REMARK)
                    VALUES
                    (:unitsn, :linename, :wono, :partno, :sync_type, :acc_count, :hulu_count, SYSDATE, :operator, :result, :remark)
                """, {
                    'unitsn': record.get('unitsn', '')[:100] if record.get('unitsn') else None,
                    'linename': linename[:20] if linename else None,
                    'wono': wono[:50] if wono else None,
                    'partno': partno[:50] if partno else None,
                    'sync_type': record.get('sync_type', '')[:20] if record.get('sync_type') else None,
                    'acc_count': record.get('acc_count', 1),
                    'hulu_count': record.get('hulu_count', 1),
                    'operator': operator[:50] if operator else None,
                    'result': record.get('result', 'SUCCESS')[:10],
                    'remark': record.get('remark', '')[:200] if record.get('remark') else None
                })
            except Exception as e:
                print(f"[LOG ERROR] batch insert single record failed: {e}")
                continue

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        # 日志记录失败不影响主业务
        print(f"[LOG ERROR] log_hulu_sync_batch failed: {e}")

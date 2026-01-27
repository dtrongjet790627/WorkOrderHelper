# -*- coding: utf-8 -*-
"""ERP相关路由"""

from flask import Blueprint, request, jsonify
from io import BytesIO
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from models.acc_db import get_connection
from models.erp_db import get_erp_connection
from utils.line_identifier import identify_line

erp_bp = Blueprint('erp', __name__)


@erp_bp.route('/api/upload_erp', methods=['POST'])
def upload_erp():
    """上传ERP Excel文件并解析"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '未上传文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '未选择文件'}), 400

        # 读取Excel
        df = pd.read_excel(BytesIO(file.read()))
        df = df.iloc[:-1]  # 排除合计行

        wono = str(df.iloc[0, 4])
        partno = str(df.iloc[0, 6])

        # 按批号汇总
        batch_data = {}
        for idx, row in df.iterrows():
            batch = str(row.iloc[19])
            qty = int(row.iloc[13])
            batch_data[batch] = batch_data.get(batch, 0) + qty

        erp_data = [{'packid': k, 'qty': v} for k, v in sorted(batch_data.items())]
        total = sum(batch_data.values())

        return jsonify({
            'wono': wono,
            'partno': partno,
            'batches': erp_data,
            'total': total
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@erp_bp.route('/api/sync_data', methods=['POST'])
def sync_data():
    """同步数据 - 执行收货调整"""
    try:
        data = request.json
        wono = data.get('wono')
        erp_batches = data.get('erp_batches', [])

        if not wono or not erp_batches:
            return jsonify({'error': '参数不完整'}), 400

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        results = []

        # 查询当前数据库中各批次数量
        erp_dict = {b['packid']: b['qty'] for b in erp_batches}

        cursor.execute("""
            SELECT packid, COUNT(*) AS qty
            FROM epr_report_work_history
            WHERE wono = :wono
            GROUP BY packid
        """, {'wono': wono})

        db_batches = {row[0]: row[1] for row in cursor.fetchall()}

        # 对比并删除多余记录
        for packid, db_qty in db_batches.items():
            erp_qty = erp_dict.get(packid, 0)
            if db_qty > erp_qty:
                delete_count = db_qty - erp_qty
                cursor.execute("""
                    DELETE FROM epr_report_work_history
                    WHERE ROWID IN (
                        SELECT ROWID FROM (
                            SELECT ROWID FROM epr_report_work_history
                            WHERE wono = :wono AND packid = :packid
                            ORDER BY report_time DESC
                        ) WHERE ROWNUM <= :cnt
                    )
                """, {'wono': wono, 'packid': packid, 'cnt': delete_count})

                results.append(f"epr_report_work_history: 批次{packid}删除{delete_count}条")

        conn.commit()

        # 同步pack_history
        cursor.execute("""
            DELETE FROM pack_history ph
            WHERE EXISTS (
                SELECT 1 FROM acc_wo_workorder_detail awd
                WHERE awd.unitsn = ph.unitsn
                AND awd.wono = :wono
                AND awd.status = 2
                AND awd.line = ph.line
            )
            AND NOT EXISTS (
                SELECT 1 FROM epr_report_work_history erh
                WHERE erh.unitsn = ph.unitsn
                AND erh.wono = :wono
            )
        """, {'wono': wono})

        if cursor.rowcount > 0:
            results.append(f"pack_history: 删除{cursor.rowcount}条多余记录")

        conn.commit()

        # 更新pack_info
        cursor.execute("""
            SELECT
                ph.packid,
                COUNT(*) AS actual_qty,
                pi.currquantity
            FROM pack_history ph
            JOIN pack_info pi ON ph.packid = pi.packid
            WHERE ph.packid IN (
                SELECT DISTINCT ph2.packid FROM pack_history ph2
                WHERE EXISTS (
                    SELECT 1 FROM acc_wo_workorder_detail awd
                    WHERE awd.unitsn = ph2.unitsn AND awd.wono = :wono AND awd.status = 2
                )
            )
            GROUP BY ph.packid, pi.currquantity
            HAVING COUNT(*) != pi.currquantity
        """, {'wono': wono})

        for row in cursor.fetchall():
            packid, actual_qty, curr_qty = row
            cursor.execute("""
                UPDATE pack_info SET currquantity = :qty, lastupdatetime = SYSDATE
                WHERE packid = :packid
            """, {'qty': actual_qty, 'packid': packid})
            results.append(f"pack_info: 批次{packid} {curr_qty}->{actual_qty}")

        conn.commit()

        # 查询缺失记录
        cursor.execute("""
            SELECT COUNT(*)
            FROM acc_wo_workorder_detail awd
            WHERE awd.wono = :wono AND awd.status = 2
            AND NOT EXISTS (
                SELECT 1 FROM pack_history ph
                WHERE ph.unitsn = awd.unitsn AND ph.line = awd.line
            )
        """, {'wono': wono})

        missing_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'results': results,
            'missing_count': missing_count,
            'message': f'同步完成，还有{missing_count}条记录待补充' if missing_count > 0 else '同步完成'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@erp_bp.route('/api/query_erp_packs', methods=['POST'])
def query_erp_packs():
    """从ERP数据库直接查询工单的批次汇总"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        erp_conn = get_erp_connection(wono)
        erp_cursor = erp_conn.cursor()

        erp_cursor.execute("""
            SELECT
                e.FLOT_TEXT AS packid,
                SUM(e.FQUAQTY) AS qty
            FROM T_PRD_MORPTENTRY e
            JOIN T_PRD_MORPT h ON e.FID = h.FID
            WHERE e.FMOBILLNO = %s
            GROUP BY e.FLOT_TEXT
            ORDER BY e.FLOT_TEXT
        """, (wono,))

        erp_packs = []
        erp_total = 0
        for row in erp_cursor.fetchall():
            qty = int(row[1]) if row[1] else 0
            erp_packs.append({
                'packid': row[0],
                'qty': qty
            })
            erp_total += qty

        erp_cursor.close()
        erp_conn.close()

        return jsonify({
            'success': True,
            'wono': wono,
            'source': 'ERP',
            'erp_packs': erp_packs,
            'erp_total': erp_total
        })

    except Exception as e:
        return jsonify({'error': f'ERP查询失败: {str(e)}'}), 500


@erp_bp.route('/api/erp_order_summary', methods=['POST'])
def erp_order_summary():
    """获取ERP工单概述信息"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        erp_conn = get_erp_connection(wono)
        erp_cursor = erp_conn.cursor()

        erp_cursor.execute("""
            SELECT
                h.FBILLNO,
                m.FNUMBER AS material_no,
                ml.FNAME AS material_name,
                e.FQTY AS plan_qty,
                ea.FSTOCKINQUASELQTY AS in_stock_qty,
                ea.FSTATUS AS biz_status,
                ea.FCLOSEDATE AS close_date
            FROM T_PRD_MO h
            JOIN T_PRD_MOENTRY e ON h.FID = e.FID
            JOIN T_PRD_MOENTRY_A ea ON e.FENTRYID = ea.FENTRYID
            LEFT JOIN T_BD_MATERIAL m ON e.FMATERIALID = m.FMATERIALID
            LEFT JOIN T_BD_MATERIAL_L ml ON m.FMATERIALID = ml.FMATERIALID AND ml.FLOCALEID = 2052
            WHERE h.FBILLNO = %s
        """, (wono,))

        mo_row = erp_cursor.fetchone()

        if not mo_row:
            erp_cursor.close()
            erp_conn.close()
            return jsonify({
                'success': True,
                'wono': wono,
                'mo_bill_no': wono,
                'material_no': '-',
                'material_name': '-',
                'plan_qty': 0,
                'in_stock_qty': 0,
                'biz_status': '-',
                'biz_status_text': '未找到',
                'close_date': '-'
            })

        mo_bill_no = mo_row[0] or wono
        material_no = mo_row[1] or '-'
        material_name = mo_row[2] or '-'
        plan_qty = int(mo_row[3]) if mo_row[3] else 0
        in_stock_qty = int(mo_row[4]) if mo_row[4] else 0
        biz_status = mo_row[5] or '-'
        close_date = mo_row[6]

        if close_date:
            close_date = close_date.strftime('%Y-%m-%d') if hasattr(close_date, 'strftime') else str(close_date)[:10]
        else:
            close_date = '-'

        biz_status_map = {
            '1': '计划',
            '2': '计划确认',
            '3': '下达',
            '4': '开工',
            '6': '结案',
            '7': '关闭'
        }
        biz_status_text = biz_status_map.get(str(biz_status), str(biz_status))

        erp_cursor.close()
        erp_conn.close()

        return jsonify({
            'success': True,
            'wono': wono,
            'mo_bill_no': mo_bill_no,
            'material_no': material_no,
            'material_name': material_name,
            'plan_qty': plan_qty,
            'in_stock_qty': in_stock_qty,
            'biz_status': biz_status,
            'biz_status_text': biz_status_text,
            'close_date': close_date
        })

    except Exception as e:
        return jsonify({'error': f'ERP工单概述查询失败: {str(e)}'}), 500


def _query_erp_data(wono):
    """查询ERP数据（独立函数，用于并行执行）"""
    erp_conn = get_erp_connection(wono)
    erp_cursor = erp_conn.cursor()

    # 查询ERP收货记录数
    erp_cursor.execute("""
        SELECT COUNT(*) AS batch_count
        FROM T_PRD_MORPTENTRY e
        JOIN T_PRD_MORPT h ON e.FID = h.FID
        WHERE e.FMOBILLNO = %s
    """, (wono,))
    erp_batch_count_row = erp_cursor.fetchone()
    erp_batch_count = int(erp_batch_count_row[0]) if erp_batch_count_row else 0

    # 查询ERP每条收货记录
    erp_cursor.execute("""
        SELECT
            e.FLOT_TEXT AS packid,
            e.FQUAQTY AS qty,
            h.FBILLNO AS bill_no,
            h.FCREATEDATE AS create_date,
            h.FDOCUMENTSTATUS AS doc_status,
            u.FNAME AS approver_name,
            ea.FSTOCKINSELQTY AS stock_in_qty,
            h.FAPPROVEDATE AS approve_date,
            cu.FNAME AS creator_name
        FROM T_PRD_MORPTENTRY e
        JOIN T_PRD_MORPT h ON e.FID = h.FID
        LEFT JOIN T_PRD_MORPTENTRY_A ea ON e.FENTRYID = ea.FENTRYID
        LEFT JOIN T_SEC_USER u ON h.FAPPROVERID = u.FUSERID
        LEFT JOIN T_SEC_USER cu ON h.FCREATORID = cu.FUSERID
        WHERE e.FMOBILLNO = %s
        ORDER BY CAST(SUBSTRING(h.FBILLNO, 5, 20) AS BIGINT) DESC
    """, (wono,))

    erp_records = []
    erp_dict = {}
    erp_total = 0
    doc_status_map = {
        'A': '创建',
        'B': '审核中',
        'C': '已审核',
        'D': '已关闭',
        'Z': '暂存'
    }
    for row in erp_cursor.fetchall():
        packid = row[0]
        qty = int(row[1]) if row[1] else 0
        bill_no = row[2] if len(row) > 2 else ''
        create_date = row[3] if len(row) > 3 else None
        doc_status = row[4] if len(row) > 4 else ''
        approver_name = row[5] if len(row) > 5 else ''
        stock_in_qty = int(row[6]) if len(row) > 6 and row[6] else 0
        approve_date = row[7] if len(row) > 7 else None
        creator_name = row[8] if len(row) > 8 else ''
        # 创建日期格式化（含时分秒）
        if create_date:
            create_date_str = create_date.strftime('%Y-%m-%d %H:%M:%S') if hasattr(create_date, 'strftime') else str(create_date)[:19]
        else:
            create_date_str = ''
        # 审核日期格式化（含时分秒）
        if approve_date:
            approve_date_str = approve_date.strftime('%Y-%m-%d %H:%M:%S') if hasattr(approve_date, 'strftime') else str(approve_date)[:19]
        else:
            approve_date_str = ''
        # 创建人映射：superman -> 系统
        if creator_name and creator_name.lower() == 'superman':
            creator_name = '系统'
        doc_status_text = doc_status_map.get(doc_status, doc_status) if doc_status else ''
        erp_records.append({
            'packid': packid,
            'qty': qty,
            'bill_no': bill_no,
            'create_date': create_date_str,
            'doc_status': doc_status_text,
            'approver_name': approver_name or '',
            'stock_in_qty': stock_in_qty,
            'approve_date': approve_date_str,
            'creator_name': creator_name or ''
        })
        erp_dict[packid] = erp_dict.get(packid, 0) + qty
        erp_total += qty

    erp_cursor.close()
    erp_conn.close()

    return {
        'erp_records': erp_records,
        'erp_dict': erp_dict,
        'erp_total': erp_total,
        'erp_batch_count': erp_batch_count
    }


def _query_acc_data(wono, line_key):
    """查询ACC数据（独立函数，用于并行执行）"""
    acc_conn = get_connection(line_key)
    acc_cursor = acc_conn.cursor()

    acc_cursor.execute("""
        SELECT ph.packid, COUNT(*) AS qty, MAX(pi.status) AS pack_status
        FROM pack_history ph
        LEFT JOIN pack_info pi ON ph.packid = pi.packid
        WHERE EXISTS (
            SELECT 1 FROM acc_wo_workorder_detail awd
            WHERE awd.unitsn = ph.unitsn
            AND awd.wono = :wono
            AND awd.status = 2
            AND awd.line = ph.line
        )
        GROUP BY ph.packid
        ORDER BY ph.packid
    """, {'wono': wono})

    acc_dict = {}
    acc_status_dict = {}
    acc_total = 0
    for row in acc_cursor.fetchall():
        packid = row[0]
        qty = row[1]
        pack_status = row[2] if len(row) > 2 else None
        acc_dict[packid] = qty
        acc_status_dict[packid] = pack_status
        acc_total += qty

    # 查询pack_info表获取包装数量
    pack_total_qty_dict = {}
    all_acc_packids = list(acc_dict.keys())
    if all_acc_packids:
        batch_size = 100
        for i in range(0, len(all_acc_packids), batch_size):
            batch_packids = all_acc_packids[i:i+batch_size]
            placeholders = ','.join([':p' + str(j) for j in range(len(batch_packids))])
            params = {'p' + str(j): batch_packids[j] for j in range(len(batch_packids))}
            acc_cursor.execute(f"""
                SELECT packid, status, currquantity
                FROM pack_info
                WHERE packid IN ({placeholders})
            """, params)
            for row in acc_cursor.fetchall():
                packid = row[0]
                pack_total_qty_dict[packid] = int(row[2]) if row[2] else 0

    # 查询混装批次详情（包装数量 != 工单数量时，说明有多工单混装）
    mixed_detail_dict = {}
    if all_acc_packids:
        batch_size = 100
        for i in range(0, len(all_acc_packids), batch_size):
            batch_packids = all_acc_packids[i:i+batch_size]
            placeholders = ','.join([':p' + str(j) for j in range(len(batch_packids))])
            params = {'p' + str(j): batch_packids[j] for j in range(len(batch_packids))}
            # 查询每个批次中各工单的数量
            acc_cursor.execute(f"""
                SELECT ph.packid, awd.wono, COUNT(*) AS qty
                FROM pack_history ph
                JOIN acc_wo_workorder_detail awd ON ph.unitsn = awd.unitsn AND ph.line = awd.line
                WHERE ph.packid IN ({placeholders})
                AND awd.status = 2
                GROUP BY ph.packid, awd.wono
                ORDER BY ph.packid, qty DESC
            """, params)
            for row in acc_cursor.fetchall():
                packid = row[0]
                wo = row[1]
                qty = int(row[2]) if row[2] else 0
                if packid not in mixed_detail_dict:
                    mixed_detail_dict[packid] = []
                mixed_detail_dict[packid].append({'wono': wo, 'qty': qty})

    # 查询ACC报工成功记录 - 按汇报单号(SCHB_NUMBER)索引
    acc_report_dict = {}  # 按汇报单号索引
    acc_report_by_packid = {}  # 按批次号索引（保留兼容性）
    acc_cursor.execute("""
        SELECT PACKID, SCHB_NUMBER, CNT, REPORT_TIME, IS_SUCCESS
        FROM ACC_ERP_REPORT_SUCCESS
        WHERE WONO = :wono
    """, {'wono': wono})
    for row in acc_cursor.fetchall():
        packid = row[0]
        schb_number = row[1]
        cnt = int(row[2]) if row[2] else 0
        report_time = row[3]
        is_success = int(row[4]) if row[4] is not None else None
        if report_time:
            report_time_str = report_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(report_time, 'strftime') else str(report_time)
        else:
            report_time_str = ''
        record = {
            'packid': packid,
            'schb_number': schb_number,
            'cnt': cnt,
            'report_time': report_time_str,
            'is_success': is_success
        }
        # 按汇报单号索引（用于与ERP记录的bill_no匹配）
        if schb_number:
            acc_report_dict[schb_number] = record
        # 同时按批次号索引（兼容其他逻辑）
        acc_report_by_packid[packid] = record

    # 查询PACK_INFO和PACK_HISTORY表获取批次包装数据
    # 按批次号统计包装数量（用于已完成的批次）
    pack_history_qty_dict = {}  # packid -> 包装数量
    acc_cursor.execute("""
        SELECT ph.packid, COUNT(*) AS qty
        FROM pack_history ph
        WHERE EXISTS (
            SELECT 1 FROM acc_wo_workorder_detail awd
            WHERE awd.unitsn = ph.unitsn
            AND awd.wono = :wono
            AND awd.status = 2
            AND awd.line = ph.line
        )
        GROUP BY ph.packid
    """, {'wono': wono})
    for row in acc_cursor.fetchall():
        packid = row[0]
        qty = int(row[1]) if row[1] else 0
        pack_history_qty_dict[packid] = qty

    # 查询未封包批次的实际包装数量（直接从pack_history统计，不限制awd.status）
    # 用于status=0的未封包批次
    pack_history_raw_qty_dict = {}  # packid -> 包装数量（不限制status条件）
    if all_acc_packids:
        batch_size = 100
        for i in range(0, len(all_acc_packids), batch_size):
            batch_packids = all_acc_packids[i:i+batch_size]
            placeholders = ','.join([':p' + str(j) for j in range(len(batch_packids))])
            params = {'p' + str(j): batch_packids[j] for j in range(len(batch_packids))}
            acc_cursor.execute(f"""
                SELECT packid, COUNT(*) AS qty
                FROM pack_history
                WHERE packid IN ({placeholders})
                GROUP BY packid
            """, params)
            for row in acc_cursor.fetchall():
                packid = row[0]
                qty = int(row[1]) if row[1] else 0
                pack_history_raw_qty_dict[packid] = qty

    acc_cursor.close()
    acc_conn.close()

    return {
        'acc_dict': acc_dict,
        'acc_status_dict': acc_status_dict,
        'acc_total': acc_total,
        'pack_total_qty_dict': pack_total_qty_dict,
        'mixed_detail_dict': mixed_detail_dict,
        'acc_report_dict': acc_report_dict,
        'acc_report_by_packid': acc_report_by_packid,
        'pack_history_qty_dict': pack_history_qty_dict,
        'pack_history_raw_qty_dict': pack_history_raw_qty_dict
    }


@erp_bp.route('/api/compare_acc_erp', methods=['POST'])
def compare_acc_erp():
    """对比ACC数据库与ERP数据库的工单包装数据"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        # 提前获取line_key（在主线程中执行，确保线程安全）
        line_key = identify_line(wono)

        # 使用线程池并行查询ERP和ACC数据
        with ThreadPoolExecutor(max_workers=2) as executor:
            erp_future = executor.submit(_query_erp_data, wono)
            acc_future = executor.submit(_query_acc_data, wono, line_key)

            # 等待两个查询完成并获取结果
            erp_result = erp_future.result()
            acc_result = acc_future.result()

        # 提取ERP查询结果
        erp_records = erp_result['erp_records']
        erp_dict = erp_result['erp_dict']
        erp_total = erp_result['erp_total']
        erp_batch_count = erp_result['erp_batch_count']

        # 提取ACC查询结果
        acc_dict = acc_result['acc_dict']
        acc_status_dict = acc_result['acc_status_dict']
        acc_total = acc_result['acc_total']
        pack_total_qty_dict = acc_result['pack_total_qty_dict']
        mixed_detail_dict = acc_result['mixed_detail_dict']
        acc_report_dict = acc_result['acc_report_dict']
        acc_report_by_packid = acc_result['acc_report_by_packid']
        pack_history_qty_dict = acc_result['pack_history_qty_dict']
        pack_history_raw_qty_dict = acc_result['pack_history_raw_qty_dict']

        # 对比分析
        all_packids = sorted(set(list(erp_dict.keys()) + list(acc_dict.keys())))

        def get_warning_type(has_acc_report_for_bill, erp_creator_name, is_duplicate=False):
            """
            判断警告类型（简化版）

            核心逻辑：只看创建人是否为系统

            参数:
                has_acc_report_for_bill: （保留参数，用于正常情况判断）
                erp_creator_name: ERP记录的创建人
                is_duplicate: 是否为重复报工

            返回值:
                None: 正常（创建人=系统）
                'duplicate_report': 重复报工
                'manual_receipt': 人工收货（创建人≠系统）
            """
            # 1. 重复报工检测
            if is_duplicate:
                return 'duplicate_report'

            # 2. 创建人不是系统 = 人工收货
            if erp_creator_name != '系统':
                return 'manual_receipt'

            # 3. 创建人是系统 = 正常
            return None

        comparison = []
        processed_packids = set()
        pack_total_qty_sum = 0

        # 重复报工检测：记录每个批次已处理的汇报单号（用于检测同一批次多次报工）
        packid_first_bill = {}  # {packid: 首次报工的bill_no}

        for erp_record in erp_records:
            packid = erp_record['packid']
            erp_qty = erp_record['qty']
            bill_no = erp_record.get('bill_no', '')
            create_date = erp_record.get('create_date', '')
            doc_status = erp_record.get('doc_status', '')
            approver_name = erp_record.get('approver_name', '')
            stock_in_qty = erp_record.get('stock_in_qty', 0)
            approve_date = erp_record.get('approve_date', '')
            creator_name = erp_record.get('creator_name', '')

            pack_status = acc_status_dict.get(packid)
            pack_total_qty = pack_total_qty_dict.get(packid, 0)
            # 按汇报单号检查是否在ACC_ERP_REPORT_SUCCESS中存在对应记录
            has_acc_report_for_bill = bill_no in acc_report_dict if bill_no else False
            acc_report_for_bill = acc_report_dict.get(bill_no) if bill_no else None

            # 重复报工检测：同一批次是否已有其他汇报单号
            is_duplicate = False
            if packid in packid_first_bill:
                # 该批次已有记录，检查是否为不同汇报单号
                if packid_first_bill[packid] != bill_no:
                    is_duplicate = True
            else:
                # 记录该批次的首次汇报单号
                packid_first_bill[packid] = bill_no

            if packid not in processed_packids:
                acc_qty = acc_dict.get(packid, 0)  # 工单数量：该批次中属于本工单的产品数
                processed_packids.add(packid)
                pack_total_qty_sum += pack_total_qty
                # 获取混装详情（包装数量 != 工单数量时有意义）
                mixed_detail = mixed_detail_dict.get(packid, [])
                status = 'main'  # 主记录
            else:
                acc_qty = None
                status = 'continuation'  # 续行
                mixed_detail = None

            # 未封包批次特殊处理
            is_unsealed = pack_status == 0 or pack_status == '0'
            if is_unsealed:
                warning_type = 'unsealed'
            else:
                # 调用简化的判断函数
                warning_type = get_warning_type(has_acc_report_for_bill, creator_name, is_duplicate)

            # 工单数量（ACC数据）和差异计算
            acc_cnt_for_bill = 0
            diff_for_bill = 0

            if warning_type == 'manual_receipt':
                # 人工收货：ACC没有报工，差异直接取负的ERP数量
                acc_cnt_for_bill = 0
                diff_for_bill = -erp_qty
            else:
                # 其他情况：正常计算
                if acc_report_for_bill:
                    acc_cnt_for_bill = acc_report_for_bill.get('cnt', 0)
                elif packid in pack_history_qty_dict:
                    acc_cnt_for_bill = pack_history_qty_dict.get(packid, 0)
                diff_for_bill = acc_cnt_for_bill - erp_qty

            comparison.append({
                'packid': packid,
                'erp_qty': erp_qty,
                'acc_qty': acc_qty,
                'status': status,
                'bill_no': bill_no,
                'create_date': create_date,
                'doc_status': doc_status,
                'approver_name': approver_name,
                'stock_in_qty': stock_in_qty,
                'pack_status': pack_status,
                'pack_total_qty': pack_total_qty,  # 包装数量：pack_info.CURRQUANTITY
                'warning_type': warning_type,
                'mixed_detail': mixed_detail,
                'has_acc_report_for_bill': has_acc_report_for_bill,
                'acc_cnt_for_bill': acc_cnt_for_bill,  # 工单数量：该批次属于本工单的产品数
                'diff_for_bill': diff_for_bill,
                'approve_date': approve_date,
                'creator_name': creator_name,
                'is_duplicate': is_duplicate
            })

        # 收集所有acc_only类型的汇报单号，批量查询ERP删除日志
        acc_only_bill_nos = []
        for packid in all_packids:
            if packid not in processed_packids:
                acc_report_record = acc_report_by_packid.get(packid)
                if acc_report_record:
                    schb_number = acc_report_record.get('schb_number', '')
                    if schb_number:
                        acc_only_bill_nos.append(schb_number)

        # 查询ERP删除日志（同时查询主表和备份表）
        erp_delete_logs = {}
        if acc_only_bill_nos:
            try:
                erp_conn2 = get_erp_connection(wono)
                erp_cursor2 = erp_conn2.cursor()
                # 批量查询删除日志
                for bill_no in acc_only_bill_nos:
                    # 在Python端构建完整的LIKE模式
                    like_pattern = f'%{bill_no}%'
                    # 先查主表，如果没有再查备份表（UNION查询）
                    erp_cursor2.execute("""
                        SELECT TOP 1 FDATETIME, FDESCRIPTION, FNAME, FIPADDRESS FROM (
                            SELECT l.FDATETIME, l.FDESCRIPTION, u.FNAME, l.FIPADDRESS
                            FROM T_BAS_OPERATELOG l
                            LEFT JOIN T_SEC_USER u ON l.FUSERID = u.FUSERID
                            WHERE l.FOBJECTTYPEID = 'PRD_MORPT'
                              AND l.FOPERATENAME LIKE N'%%删%%'
                              AND l.FDESCRIPTION LIKE %s
                            UNION ALL
                            SELECT l.FDATETIME, l.FDESCRIPTION, u.FNAME, l.FIPADDRESS
                            FROM T_BAS_OPERATELOGBK l
                            LEFT JOIN T_SEC_USER u ON l.FUSERID = u.FUSERID
                            WHERE l.FOBJECTTYPEID = 'PRD_MORPT'
                              AND l.FOPERATENAME LIKE N'%%删%%'
                              AND l.FDESCRIPTION LIKE %s
                        ) AS combined
                        ORDER BY FDATETIME DESC
                    """, (like_pattern, like_pattern))
                    row = erp_cursor2.fetchone()
                    if row:
                        delete_time = row[0]
                        if delete_time and hasattr(delete_time, 'strftime'):
                            delete_time_str = delete_time.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            delete_time_str = str(delete_time)[:19] if delete_time else ''
                        erp_delete_logs[bill_no] = {
                            'delete_time': delete_time_str,
                            'description': row[1] or '',
                            'delete_user': row[2] or '',
                            'ip_address': row[3] or ''
                        }
                erp_cursor2.close()
                erp_conn2.close()
            except Exception as e:
                # 查询删除日志失败不影响主流程
                pass

        # 处理ACC有记录但ERP无记录的批次（ERP人为删除）
        for packid in all_packids:
            if packid not in processed_packids:
                acc_qty = acc_dict.get(packid, 0)
                pack_status = acc_status_dict.get(packid)
                acc_report_record = acc_report_by_packid.get(packid)
                mixed_detail = mixed_detail_dict.get(packid, [])

                is_unsealed = pack_status == 0 or pack_status == '0'

                # 包装数量
                if is_unsealed:
                    pack_total_qty = pack_history_raw_qty_dict.get(packid, 0)
                else:
                    pack_total_qty = pack_total_qty_dict.get(packid, 0)
                    if pack_total_qty == 0:
                        pack_total_qty = pack_history_qty_dict.get(packid, 0)

                pack_total_qty_sum += pack_total_qty

                if is_unsealed:
                    # 未封包批次
                    comparison.append({
                        'packid': packid,
                        'erp_qty': 0,
                        'acc_qty': acc_qty,
                        'status': 'packing',
                        'bill_no': '-',
                        'create_date': '-',
                        'doc_status': '',
                        'approver_name': '',
                        'stock_in_qty': 0,
                        'pack_status': pack_status,
                        'pack_total_qty': pack_total_qty,
                        'warning_type': 'unsealed',
                        'mixed_detail': mixed_detail,
                        'approve_date': '',
                        'creator_name': '-',
                        'acc_cnt_for_bill': acc_qty,
                        'has_acc_report_for_bill': False,
                        'is_acc_data': False,
                        'delete_log': {},
                        'diff_for_bill': None
                    })
                elif acc_report_record and acc_report_record.get('is_success') == 1:
                    # ACC有报工成功记录但ERP无记录 -> ERP人为删除
                    acc_schb_number = acc_report_record.get('schb_number', '')
                    acc_cnt = acc_report_record.get('cnt', 0)
                    acc_report_time = acc_report_record.get('report_time', '')
                    delete_log = erp_delete_logs.get(acc_schb_number, {})

                    comparison.append({
                        'packid': packid,
                        'erp_qty': 0,
                        'acc_qty': acc_qty,
                        'status': 'acc_only',
                        'bill_no': acc_schb_number,
                        'create_date': acc_report_time,
                        'doc_status': '',
                        'approver_name': '',
                        'stock_in_qty': 0,
                        'pack_status': pack_status if pack_status else 2,
                        'pack_total_qty': pack_total_qty,
                        'warning_type': 'erp_deleted',  # ERP人为删除
                        'mixed_detail': mixed_detail,
                        'approve_date': '',
                        'creator_name': 'ACC系统',
                        'acc_cnt_for_bill': acc_cnt,
                        'has_acc_report_for_bill': True,
                        'is_acc_data': True,
                        'delete_log': delete_log,
                        'diff_for_bill': acc_cnt  # 差异=ACC数量（因为ERP为0）
                    })
                else:
                    # 已封包但ACC无报工记录（待报工状态）
                    comparison.append({
                        'packid': packid,
                        'erp_qty': 0,
                        'acc_qty': acc_qty,
                        'status': 'pending_report',
                        'bill_no': '-',
                        'create_date': '-',
                        'doc_status': '',
                        'approver_name': '',
                        'stock_in_qty': 0,
                        'pack_status': pack_status,
                        'pack_total_qty': pack_total_qty,
                        'warning_type': 'pending_report',  # 待报工
                        'mixed_detail': mixed_detail,
                        'approve_date': '',
                        'creator_name': '-',
                        'acc_cnt_for_bill': acc_qty,
                        'has_acc_report_for_bill': False,
                        'is_acc_data': False,
                        'delete_log': {},
                        'diff_for_bill': None
                    })

        # 统计
        main_records = [c for c in comparison if c['status'] != 'continuation']
        match_count = sum(1 for c in main_records if c['status'] == 'match')

        sealed_comparison = []
        packing_comparison = []
        sealed_acc_total = 0
        sealed_erp_total = 0

        for item in comparison:
            pack_status = item.get('pack_status')
            warning_type = item.get('warning_type')

            # 判断是否应计入差异统计：
            # 1. pack_status=2（ACC已封包）
            # 2. warning_type为manual_receipt（人工收货）- ERP有记录但创建人非系统
            # 3. warning_type为erp_deleted（ERP删除）- ACC有报工成功记录但ERP无记录
            # 注意：duplicate_report（重复报工）不计入差异统计
            is_sealed = (pack_status == 2 or str(pack_status) == '2')
            is_erp_confirmed = warning_type in ('manual_receipt', 'erp_deleted')
            is_duplicate = warning_type == 'duplicate_report'

            if is_duplicate:
                # 重复报工：单独归类，不计入差异统计
                item['batch_status'] = 'duplicate'
                sealed_comparison.append(item)  # 仍然显示在列表中
                # 不累加到 sealed_acc_total 和 sealed_erp_total
            elif is_sealed or is_erp_confirmed:
                item['batch_status'] = 'sealed'
                sealed_comparison.append(item)
                if item.get('acc_qty') is not None:
                    sealed_acc_total += item.get('acc_qty', 0)
                if item.get('status') != 'continuation':
                    sealed_erp_total += item.get('erp_qty', 0)
            else:
                item['batch_status'] = 'packing'
                packing_comparison.append(item)

        sealed_diff_total = sealed_acc_total - sealed_erp_total

        # 统计各类异常批次数量
        all_main_records = [c for c in comparison if c.get('status') != 'continuation']

        # 重复报工批次数量（单独统计，不计入差异）
        # 注意：重复报工的status是continuation，但warning_type是duplicate_report
        # 所以需要从全部comparison中统计，而不是all_main_records
        duplicate_count = sum(1 for c in comparison if c.get('warning_type') == 'duplicate_report')

        # 差异不为0的批次数量（排除重复报工）
        mismatch_count = sum(1 for c in all_main_records
                           if c.get('warning_type') != 'duplicate_report'
                           and c.get('diff_for_bill') is not None
                           and c.get('diff_for_bill') != 0)

        # 计算差异合计（排除重复报工）
        sealed_main_records = [c for c in sealed_comparison
                              if c.get('status') != 'continuation'
                              and c.get('warning_type') != 'duplicate_report']
        sealed_diff_sum = 0
        for item in sealed_main_records:
            if item.get('diff_for_bill') is not None:
                sealed_diff_sum += item.get('diff_for_bill', 0)

        return jsonify({
            'success': True,
            'wono': wono,
            'erp_total': erp_total,
            'erp_batch_count': erp_batch_count,
            'acc_total': acc_total,
            'diff_total': sealed_diff_total,  # 卡片差异只计算已封包批次
            'sealed_diff_total': sealed_diff_total,
            'sealed_acc_total': sealed_acc_total,
            'sealed_erp_total': sealed_erp_total,
            'comparison': comparison,
            'sealed_comparison': sealed_comparison,
            'packing_comparison': packing_comparison,
            'summary': {
                'total_batches': len(comparison),
                'sealed_batches': len(sealed_comparison),
                'packing_batches': len(packing_comparison),
                'match_count': len(all_main_records) - mismatch_count - duplicate_count,
                'mismatch_count': mismatch_count,
                'duplicate_count': duplicate_count  # 重复报工批次数量
            },
            'summary_row': {
                'pack_total_qty_sum': pack_total_qty_sum,
                'erp_qty_sum': erp_total,
                'acc_qty_sum': acc_total,
                'diff_sum': sealed_diff_sum
            }
        })

    except Exception as e:
        return jsonify({'error': f'对比失败: {str(e)}'}), 500

# -*- coding: utf-8 -*-
"""打包相关路由"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from models.acc_db import get_connection
from utils.line_identifier import identify_line
from utils.permission import check_user_permission
from utils.operation_log import log_packing_op
from utils.logger import log_user

packing_bp = Blueprint('packing', __name__)


@packing_bp.route('/api/query_unpacked_products', methods=['POST'])
def query_unpacked_products():
    """查询完工但未打包的产品"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 查询工单基本信息
        cursor.execute("""
            SELECT wono, partno, line, COUNT(*) as total,
                   SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) as completed,
                   SUM(CASE WHEN status = 2 AND packingno IS NULL THEN 1 ELSE 0 END) as unpacked
            FROM acc_wo_workorder_detail
            WHERE wono = :wono AND isdelete = 0
            GROUP BY wono, partno, line
        """, {'wono': wono})
        summary_row = cursor.fetchone()

        if not summary_row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到工单 {wono}'}), 404

        summary = {
            'wono': summary_row[0],
            'partno': summary_row[1],
            'line': summary_row[2],
            'total': summary_row[3],
            'completed': summary_row[4],
            'unpacked': summary_row[5]
        }

        # 查询未打包产品列表
        cursor.execute("""
            SELECT awd.unitsn, awd.partno, awd.line, awd.status, awd.packingno, awd.mtime
            FROM acc_wo_workorder_detail awd
            WHERE awd.wono = :wono
              AND awd.status = 2
              AND awd.line = :wo_line
              AND NOT EXISTS (
                  SELECT 1 FROM pack_history ph
                  WHERE ph.unitsn = awd.unitsn AND ph.line = :wo_line
              )
            ORDER BY awd.unitsn
        """, {'wono': wono, 'wo_line': summary['line']})

        unpacked_products = []
        for row in cursor.fetchall():
            unpacked_products.append({
                'unitsn': row[0],
                'partno': row[1],
                'line': row[2],
                'status': row[3],
                'packingno': row[4],
                'mtime': str(row[5]) if row[5] else None
            })

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'wono': wono,
            'summary': summary,
            'unpacked_products': unpacked_products,
            'unpacked_count': len(unpacked_products)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@packing_bp.route('/api/get_pack_batches', methods=['POST'])
def get_pack_batches():
    """获取可用的目标批次和参考批次"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 获取工单的partno
        cursor.execute("""
            SELECT DISTINCT partno, line FROM acc_wo_workorder_detail
            WHERE wono = :wono AND ROWNUM = 1
        """, {'wono': wono})
        wo_row = cursor.fetchone()
        if not wo_row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到工单 {wono}'}), 404

        partno = wo_row[0]
        wo_line = wo_row[1]

        # 查询可用目标批次
        cursor.execute("""
            SELECT packid, prodtype, currquantity, status, lastupdatetime,
                   ROW_NUMBER() OVER (ORDER BY lastupdatetime DESC) AS rn
            FROM pack_info
            WHERE prodtype = :partno AND currquantity = 0
            ORDER BY lastupdatetime DESC
        """, {'partno': partno})

        target_batches = []
        for row in cursor.fetchall():
            target_batches.append({
                'packid': row[0],
                'prodtype': row[1],
                'currquantity': row[2],
                'status': row[3],
                'lastupdatetime': str(row[4]) if row[4] else None,
                'rank': row[5]
            })

        # 查询参考批次
        cursor.execute("""
            SELECT packid, stn, drag, generatorname, customerpackid, customerpartno
            FROM (
                SELECT packid, stn, drag, generatorname, customerpackid, customerpartno,
                       ROW_NUMBER() OVER (ORDER BY lastupdatetime DESC) AS rn
                FROM pack_info
                WHERE prodtype = :partno AND status = 2 AND currquantity > 0
            ) WHERE rn = 1
        """, {'partno': partno})
        ref_row = cursor.fetchone()

        reference_batch = None
        if ref_row:
            reference_batch = {
                'packid': ref_row[0],
                'stn': ref_row[1],
                'drag': ref_row[2],
                'generatorname': ref_row[3],
                'customerpackid': ref_row[4],
                'customerpartno': ref_row[5]
            }

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'wono': wono,
            'partno': partno,
            'line': wo_line,
            'target_batches': target_batches,
            'reference_batch': reference_batch,
            'recommended_batch': target_batches[1]['packid'] if len(target_batches) > 1 else (target_batches[0]['packid'] if target_batches else None)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@packing_bp.route('/api/generate_pack_id', methods=['POST'])
def generate_pack_id():
    """自动生成新批次号并创建pack_info记录"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        operator_id = data.get('operator_id', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 获取工单的partno和line
        cursor.execute("""
            SELECT DISTINCT partno, line FROM acc_wo_workorder_detail
            WHERE wono = :wono AND ROWNUM = 1
        """, {'wono': wono})
        wo_row = cursor.fetchone()
        if not wo_row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到工单 {wono}'}), 404

        partno = wo_row[0]
        wo_line = wo_row[1] or ''

        # 查询历史批次提取固定编码
        cursor.execute("""
            SELECT packid FROM (
                SELECT packid FROM pack_info
                WHERE prodtype = :partno
                AND packid IS NOT NULL
                AND LENGTH(packid) = 16
                ORDER BY lastupdatetime DESC NULLS LAST
            ) WHERE ROWNUM = 1
        """, {'partno': partno})

        row = cursor.fetchone()
        if row is None or row[0] is None:
            cursor.close()
            conn.close()
            return jsonify({'error': f'产品型号 {partno} 没有历史批次，无法提取固定编码'}), 400

        history_packid = row[0]
        fixed_code = history_packid[8:11]

        # 查询全局最大序号
        cursor.execute("""
            SELECT packid FROM (
                SELECT packid FROM pack_info
                WHERE SUBSTR(packid, 9, 3) = :fixed_code
                AND LENGTH(packid) = 16
                ORDER BY packid DESC
            ) WHERE ROWNUM = 1
        """, {'fixed_code': fixed_code})
        max_row = cursor.fetchone()

        # 生成新批次号
        today = datetime.now().strftime('%Y%m%d')
        if max_row and max_row[0]:
            max_packid = max_row[0]
            try:
                max_seq = int(max_packid[11:16])
                new_seq = max_seq + 1
            except ValueError:
                new_seq = 1
        else:
            new_seq = 1

        new_pack_id = f"{today}{fixed_code}{new_seq:05d}"

        # 获取产品型号的PACKSIZE
        packsize = _get_packsize(cursor, partno)

        # 获取参考批次信息
        cursor.execute("""
            SELECT stn, drag, generatorname, customerpackid, customerpartno
            FROM (
                SELECT stn, drag, generatorname, customerpackid, customerpartno,
                       ROW_NUMBER() OVER (ORDER BY lastupdatetime DESC NULLS LAST) AS rn
                FROM pack_info
                WHERE prodtype = :partno AND status = 2 AND currquantity > 0
            ) WHERE rn = 1
        """, {'partno': partno})
        ref_row = cursor.fetchone()

        ref_stn = ref_row[0] if ref_row else None
        ref_drag = ref_row[1] if ref_row else None
        ref_generatorname = ref_row[2] if ref_row else None
        ref_customerpackid = ref_row[3] if ref_row else None
        ref_customerpartno = ref_row[4] if ref_row else None

        # 创建新的pack_info记录（status=2防止生产线插入数据导致混装）
        cursor.execute("""
            INSERT INTO pack_info
            (packid, prodtype, packsize, currquantity, status, lastupdate, lastupdatetime,
             line, stn, drag, generatorname, customerpackid, customerpartno)
            VALUES
            (:packid, :prodtype, :packsize, 0, 2, SYSDATE, SYSDATE,
             :line, :stn, :drag, :generatorname, :customerpackid, :customerpartno)
        """, {
            'packid': new_pack_id,
            'prodtype': partno,
            'packsize': packsize,
            'line': wo_line,
            'stn': ref_stn,
            'drag': ref_drag,
            'generatorname': ref_generatorname,
            'customerpackid': ref_customerpackid,
            'customerpartno': ref_customerpartno
        })

        conn.commit()
        cursor.close()
        conn.close()

        # 不再记录GENERATE_PACKID日志，打包时会记录每个unitsn的日志

        return jsonify({
            'success': True,
            'pack_id': new_pack_id,
            'partno': partno,
            'line': wo_line
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _get_packsize(cursor, partno):
    """获取产品型号的标准包装数量"""
    cursor.execute("""
        SELECT packsize FROM (
            SELECT packsize FROM pack_info
            WHERE prodtype = :partno AND packsize > 0
            ORDER BY lastupdate DESC NULLS LAST
        ) WHERE ROWNUM = 1
    """, {'partno': partno})
    row = cursor.fetchone()
    return row[0] if row and row[0] else 300  # 默认300


def _generate_new_packid(cursor, partno, wo_line, ref_info):
    """生成新批次号并创建pack_info记录"""
    # 查询历史批次提取固定编码
    cursor.execute("""
        SELECT packid FROM (
            SELECT packid FROM pack_info
            WHERE prodtype = :partno
            AND packid IS NOT NULL
            AND LENGTH(packid) = 16
            ORDER BY lastupdatetime DESC NULLS LAST
        ) WHERE ROWNUM = 1
    """, {'partno': partno})
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return None

    history_packid = row[0]
    fixed_code = history_packid[8:11]

    # 查询全局最大序号
    cursor.execute("""
        SELECT packid FROM (
            SELECT packid FROM pack_info
            WHERE SUBSTR(packid, 9, 3) = :fixed_code
            AND LENGTH(packid) = 16
            ORDER BY packid DESC
        ) WHERE ROWNUM = 1
    """, {'fixed_code': fixed_code})
    max_row = cursor.fetchone()

    # 生成新批次号
    today = datetime.now().strftime('%Y%m%d')
    if max_row and max_row[0]:
        max_packid = max_row[0]
        try:
            max_seq = int(max_packid[11:16])
            new_seq = max_seq + 1
        except ValueError:
            new_seq = 1
    else:
        new_seq = 1

    new_pack_id = f"{today}{fixed_code}{new_seq:05d}"

    # 创建新的pack_info记录（status=2防止生产线插入数据导致混装）
    cursor.execute("""
        INSERT INTO pack_info
        (packid, prodtype, packsize, currquantity, status, lastupdate, lastupdatetime,
         line, stn, drag, generatorname, customerpackid, customerpartno)
        VALUES
        (:packid, :prodtype, :packsize, 0, 2, SYSDATE, SYSDATE,
         :line, :stn, :drag, :generatorname, :customerpackid, :customerpartno)
    """, {
        'packid': new_pack_id,
        'prodtype': partno,
        'packsize': ref_info.get('packsize', 300),
        'line': wo_line,
        'stn': ref_info.get('stn'),
        'drag': ref_info.get('drag'),
        'generatorname': ref_info.get('generatorname'),
        'customerpackid': ref_info.get('customerpackid'),
        'customerpartno': ref_info.get('customerpartno')
    })

    return new_pack_id


@packing_bp.route('/api/execute_packing', methods=['POST'])
def execute_packing():
    """执行补打包操作（支持PACKSIZE限制自动分包）"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        target_packid = data.get('target_packid', '').strip()
        unitsn_list = data.get('unitsn_list', [])
        reference_packid = data.get('reference_packid', '').strip()
        operator_id = data.get('operator_id', '').strip()

        # 权限校验
        permission = check_user_permission(operator_id)
        if not permission['has_permission']:
            return jsonify({
                'error': '无操作权限',
                'permission_error': True,
                'reason': permission['reason'],
                'username': permission['username']
            }), 403

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400
        if not target_packid:
            return jsonify({'error': '请选择目标批次'}), 400
        if not unitsn_list:
            return jsonify({'error': '请选择要打包的产品'}), 400

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 获取工单信息
        cursor.execute("""
            SELECT DISTINCT partno, line FROM acc_wo_workorder_detail
            WHERE wono = :wono AND ROWNUM = 1
        """, {'wono': wono})
        wo_row = cursor.fetchone()
        if not wo_row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到工单 {wono}'}), 404

        partno = wo_row[0]
        wo_line = wo_row[1]

        # 获取PACKSIZE限制
        packsize = _get_packsize(cursor, partno)

        # 获取参考批次信息
        cursor.execute("""
            SELECT stn, drag, generatorname, customerpackid, customerpartno, packsize
            FROM pack_info WHERE packid = :packid
        """, {'packid': reference_packid if reference_packid else target_packid})
        ref_row = cursor.fetchone()

        ref_info = {
            'stn': ref_row[0] if ref_row else None,
            'drag': ref_row[1] if ref_row else None,
            'generatorname': ref_row[2] if ref_row else None,
            'customerpackid': ref_row[3] if ref_row else None,
            'customerpartno': ref_row[4] if ref_row else None,
            'packsize': ref_row[5] if ref_row and ref_row[5] else packsize
        }

        # 过滤已存在的产品
        valid_unitsn_list = []
        skipped_count = 0
        results = []

        for unitsn in unitsn_list:
            cursor.execute("""
                SELECT COUNT(*) FROM pack_history
                WHERE unitsn = :unitsn AND line = :line
            """, {'unitsn': unitsn, 'line': wo_line})
            if cursor.fetchone()[0] > 0:
                results.append({'unitsn': unitsn, 'action': 'skipped', 'reason': '已存在于pack_history'})
                skipped_count += 1
            else:
                valid_unitsn_list.append(unitsn)

        # 分批打包逻辑（新包装从0开始，按PACKSIZE分批）
        inserted_count = 0
        created_packs = []  # 记录所有使用/创建的批次
        current_packid = target_packid
        current_pack_count = 0  # 当前包装已装数量

        batch_index = 0
        while batch_index < len(valid_unitsn_list):
            # 如果当前批次已满，创建新批次
            if current_pack_count >= packsize:
                new_packid = _generate_new_packid(cursor, partno, wo_line, ref_info)
                if not new_packid:
                    # 无法生成新批次，中断
                    break
                current_packid = new_packid
                current_pack_count = 0

            # 计算本批次可装数量
            remaining_capacity = packsize - current_pack_count
            batch_end = min(batch_index + remaining_capacity, len(valid_unitsn_list))
            batch_unitsn = valid_unitsn_list[batch_index:batch_end]

            # 插入pack_history
            for unitsn in batch_unitsn:
                cursor.execute("""
                    INSERT INTO pack_history
                    (packid, unitsn, packbarcode, packdate, lastupdatetime, line, stn, trwsn, customerpackid, customerpartno)
                    VALUES
                    (:packid, :unitsn, :packbarcode, SYSDATE, SYSDATE, :line, :stn, NULL, :customerpackid, :customerpartno)
                """, {
                    'packid': current_packid,
                    'unitsn': unitsn,
                    'packbarcode': unitsn,
                    'line': wo_line,
                    'stn': ref_info['stn'],
                    'customerpackid': ref_info['customerpackid'],
                    'customerpartno': ref_info['customerpartno']
                })
                inserted_count += 1
                results.append({'unitsn': unitsn, 'action': 'inserted', 'packid': current_packid})

            # 记录使用的批次
            if current_packid not in created_packs:
                created_packs.append(current_packid)

            # 更新计数
            batch_index = batch_end
            current_pack_count += len(batch_unitsn)

        # 更新所有使用的pack_info
        for packid in created_packs:
            cursor.execute("""
                SELECT COUNT(*) FROM pack_history WHERE packid = :packid
            """, {'packid': packid})
            new_qty = cursor.fetchone()[0]

            cursor.execute("""
                UPDATE pack_info
                SET currquantity = :qty,
                    status = 2,
                    lastupdate = SYSDATE,
                    lastupdatetime = SYSDATE,
                    stn = :stn,
                    drag = :drag,
                    generatorname = :generatorname,
                    customerpackid = :customerpackid,
                    customerpartno = :customerpartno
                WHERE packid = :packid
            """, {
                'qty': new_qty,
                'stn': ref_info['stn'],
                'drag': ref_info['drag'],
                'generatorname': ref_info['generatorname'],
                'customerpackid': ref_info['customerpackid'],
                'customerpartno': ref_info['customerpartno'],
                'packid': packid
            })

        conn.commit()
        cursor.close()
        conn.close()

        # 记录操作日志 - 为每个成功插入的unitsn记录一条日志
        for r in results:
            if r.get('action') == 'inserted':
                log_packing_op(
                    unitsn=r.get('unitsn'),
                    linename=wo_line,
                    wono=wono,
                    partno=partno,
                    packid=r.get('packid'),
                    operator=operator_id
                )

        # 记录用户行为日志
        if inserted_count > 0:
            log_user('MANUAL_PACKING', operator_id, f"手动补打包: {wono}",
                     wono=wono, partno=partno, line=wo_line,
                     packed_count=inserted_count, skipped_count=skipped_count,
                     packs=created_packs)

        return jsonify({
            'success': True,
            'wono': wono,
            'target_packid': target_packid,
            'packed_count': inserted_count,
            'skipped_count': skipped_count,
            'packsize': packsize,
            'created_packs': created_packs,
            'results': results
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@packing_bp.route('/api/add_missing', methods=['POST'])
def add_missing():
    """补充缺失记录到pack_history"""
    try:
        data = request.json
        wono = data.get('wono')
        operator_id = data.get('operator_id', '').strip()

        # 权限校验
        permission = check_user_permission(operator_id)
        if not permission['has_permission']:
            return jsonify({
                'error': '无操作权限',
                'permission_error': True,
                'reason': permission['reason'],
                'username': permission['username']
            }), 403

        if not wono:
            return jsonify({'error': '缺少工单号'}), 400

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 获取型号
        cursor.execute("""
            SELECT DISTINCT partno, line FROM acc_wo_workorder_detail
            WHERE wono = :wono AND status = 2
        """, {'wono': wono})
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': '未找到工单信息'}), 404

        partno, line = row

        # 找目标批次
        cursor.execute("""
            SELECT packid FROM (
                SELECT packid, ROW_NUMBER() OVER (ORDER BY lastupdatetime DESC) AS rn
                FROM pack_info
                WHERE prodtype = :partno AND currquantity = 0
            ) WHERE rn = 2
        """, {'partno': partno})
        row = cursor.fetchone()

        if not row:
            return jsonify({'error': '未找到可用的目标批次(数量为0)'}), 404

        target_packid = row[0]

        # 获取参考值
        cursor.execute("""
            SELECT packid, stn FROM (
                SELECT packid, stn, ROW_NUMBER() OVER (ORDER BY lastupdatetime DESC) AS rn
                FROM pack_info
                WHERE prodtype = :partno AND status = 2 AND currquantity > 0
            ) WHERE rn = 1
        """, {'partno': partno})
        row = cursor.fetchone()

        if not row:
            return jsonify({'error': '未找到参考批次'}), 404

        ref_packid, ref_stn = row

        # 先获取要插入的unitsn列表
        cursor.execute("""
            SELECT awd.unitsn
            FROM acc_wo_workorder_detail awd
            WHERE awd.wono = :wono AND awd.status = 2
            AND NOT EXISTS (
                SELECT 1 FROM pack_history ph
                WHERE ph.unitsn = awd.unitsn AND ph.line = awd.line
            )
        """, {'wono': wono})
        missing_unitsn_list = [row[0] for row in cursor.fetchall()]

        # 插入缺失记录
        inserted_count = 0
        for unitsn in missing_unitsn_list:
            cursor.execute("""
                INSERT INTO pack_history (packid, unitsn, packbarcode, packdate, lastupdatetime, line, stn, trwsn, customerpackid, customerpartno)
                VALUES (:target_packid, :unitsn, :unitsn, SYSDATE, SYSDATE, :line, :stn, NULL, NULL, NULL)
            """, {'target_packid': target_packid, 'unitsn': unitsn, 'line': line, 'stn': ref_stn})
            inserted_count += 1

        if inserted_count > 0:
            cursor.execute("""
                UPDATE pack_info
                SET currquantity = :qty,
                    status = 2,
                    lastupdate = SYSDATE,
                    lastupdatetime = SYSDATE,
                    stn = :stn
                WHERE packid = :packid
            """, {'qty': inserted_count, 'stn': ref_stn, 'packid': target_packid})

        conn.commit()
        cursor.close()
        conn.close()

        # 记录操作日志 - 为每个unitsn记录一条日志
        for unitsn in missing_unitsn_list:
            log_packing_op(
                unitsn=unitsn,
                linename=line,
                wono=wono,
                partno=partno,
                packid=target_packid,
                operator=operator_id
            )

        # 记录用户行为日志
        if inserted_count > 0:
            log_user('ADD_MISSING_PACK', operator_id, f"补充缺失打包: {wono}",
                     wono=wono, partno=partno, line=line,
                     packed_count=inserted_count, target_packid=target_packid)

        return jsonify({
            'success': True,
            'packed_count': inserted_count,
            'target_packid': target_packid,
            'message': f'成功插入{inserted_count}条记录到批次{target_packid}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

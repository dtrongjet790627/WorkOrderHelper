# -*- coding: utf-8 -*-
"""工单查询相关路由"""

from flask import Blueprint, request, jsonify
from config.database import LINE_CONFIG
from models.acc_db import get_connection, get_iplant_web_connection
from utils.line_identifier import identify_line
from utils.deployment import check_line_access
from utils.permission import check_user_permission
from utils.operation_log import log_workorder_op
from utils.logger import log_user

workorder_bp = Blueprint('workorder', __name__)


@workorder_bp.route('/api/query_workorder', methods=['POST'])
def query_workorder():
    """查询工单完成情况（含未加入工单产品和未打包产品）"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        line_key = identify_line(wono)
        allowed, err = check_line_access(line_key)
        if not allowed:
            return err
        line_info = LINE_CONFIG[line_key]

        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 查询工单明细
        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) AS incomplete,
                MAX(partno) AS partno,
                MAX(line) AS line
            FROM acc_wo_workorder_detail
            WHERE wono = :wono
        """, {'wono': wono})
        row = cursor.fetchone()

        if not row or row[0] == 0:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到工单 {wono}'}), 404

        partno = row[3]
        wo_line = row[4]
        wo_count = row[0]

        workorder_info = {
            'wono': wono,
            'partno': partno,
            'line': wo_line,
            'line_name': line_info['name'],
            'total': row[0],
            'completed': row[1] or 0,
            'incomplete': row[2] or 0,
            'completion_rate': round((row[1] or 0) / row[0] * 100, 2) if row[0] > 0 else 0
        }

        # 查询打包情况
        # 使用子查询先按packid分组统计数量，避免SCHB_NUMBER导致的重复计算
        cursor.execute("""
            SELECT
                sub.packid,
                sub.qty,
                pi.currquantity,
                pi.packsize,
                pi.status,
                TO_CHAR(pi.lastupdatetime, 'YYYY-MM-DD HH24:MI:SS') AS lastupdate,
                rs.SCHB_NUMBER
            FROM (
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
            ) sub
            JOIN pack_info pi ON sub.packid = pi.packid
            LEFT JOIN ACC_ERP_REPORT_SUCCESS rs ON sub.packid = rs.PACKID AND rs.WONO = :wono AND rs.IS_SUCCESS = 1
            ORDER BY sub.packid
        """, {'wono': wono})

        pack_list = []
        seen_packids = set()  # 用于去重，避免同一packid因多个SCHB_NUMBER而重复
        for row in cursor.fetchall():
            packid = row[0]
            if packid in seen_packids:
                continue  # 跳过已处理的packid
            seen_packids.add(packid)
            pack_list.append({
                'packid': packid,
                'actual_qty': row[1],
                'info_qty': row[2],
                'packsize': row[3],
                'status': '已封包' if str(row[4]) == '2' else '生产中' if str(row[4]) == '0' else str(row[4]),
                'lastupdate': row[5],
                'schb_number': row[6] if len(row) > 6 else None,
                'other_wonos': []
            })

        # 对每个批次查询混装信息
        for pack in pack_list:
            cursor.execute("""
                SELECT awd.wono, COUNT(*) AS qty
                FROM acc_wo_workorder_detail awd
                WHERE awd.unitsn IN (
                    SELECT ph.unitsn FROM pack_history ph
                    WHERE ph.packid = :packid AND ph.line = :wo_line
                )
                AND awd.line = :wo_line
                GROUP BY awd.wono
                ORDER BY awd.wono
            """, {'packid': pack['packid'], 'wo_line': wo_line})

            mixed_detail = []
            other_wonos = []
            for wo_row in cursor.fetchall():
                mixed_detail.append({
                    'wono': wo_row[0],
                    'qty': wo_row[1]
                })
                if wo_row[0] != wono:
                    other_wonos.append({
                        'wono': wo_row[0],
                        'qty': wo_row[1]
                    })

            pack['mixed_detail'] = mixed_detail
            pack['other_wonos'] = other_wonos

        # 查询ERP收货情况
        cursor.execute("""
            SELECT packid, COUNT(*) AS qty
            FROM epr_report_work_history
            WHERE wono = :wono
            GROUP BY packid
            ORDER BY packid
        """, {'wono': wono})

        erp_list = []
        erp_total = 0
        for row in cursor.fetchall():
            erp_list.append({'packid': row[0], 'qty': row[1]})
            erp_total += row[1]

        # 未加入工单产品默认不查询
        missing_products = []
        missing_summary = {'wo_count': wo_count, 'first_station_count': wo_count, 'missing_count': 0, 'need_query': True}
        first_station_info = None

        # 只查询首站信息
        cursor.execute("""
            SELECT rc.op, lpc.routename, lpc.line
            FROM acc_line_partno_cfg lpc
            INNER JOIN acc_routing_cfg rc
                ON lpc.routename = rc.routename AND lpc.line = rc.line
            WHERE lpc.partno = :partno AND rc.status = '0'
        """, {'partno': partno})
        first_station_row = cursor.fetchone()

        if first_station_row:
            first_station_info = {
                'op': first_station_row[0],
                'routename': first_station_row[1],
                'line': first_station_row[2]
            }

        # 查询未打包产品
        cursor.execute("""
            SELECT awd.unitsn, awd.partno, awd.line, awd.status, awd.packingno, awd.mtime
            FROM acc_wo_workorder_detail awd
            WHERE awd.wono = :wono AND awd.status = 2 AND awd.line = :wo_line
              AND NOT EXISTS (
                  SELECT 1 FROM pack_history ph
                  WHERE ph.unitsn = awd.unitsn AND ph.line = :wo_line
              )
            ORDER BY awd.unitsn
        """, {'wono': wono, 'wo_line': wo_line})

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

        # 记录工单查询日志（仅当有有效操作人时记录）
        operator = data.get('operator', '')
        if operator and operator not in ('未知', ''):
            log_user('QUERY_WORKORDER', operator, f"查询工单: {wono}",
                     wono=wono, partno=partno, line=line_info['name'],
                     total=workorder_info['total'], completed=workorder_info['completed'])

        return jsonify({
            'workorder': workorder_info,
            'packs': pack_list,
            'erp': erp_list,
            'erp_total': erp_total,
            'pack_total': sum(p['actual_qty'] for p in pack_list),
            'missing_products': missing_products,
            'missing_summary': missing_summary,
            'first_station': first_station_info,
            'unpacked_products': unpacked_products,
            'unpacked_count': len(unpacked_products)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@workorder_bp.route('/api/query_missing_products', methods=['POST'])
def query_missing_products():
    """查询未加入工单的产品"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        line_key = identify_line(wono)
        allowed, err = check_line_access(line_key)
        if not allowed:
            return err
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 查询工单基本信息
        cursor.execute("""
            SELECT wono, partno, COUNT(*) AS wo_count, line
            FROM acc_wo_workorder_detail
            WHERE wono = :wono
            GROUP BY wono, partno, line
        """, {'wono': wono})

        wo_row = cursor.fetchone()
        if not wo_row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到工单 {wono}'}), 404

        partno = wo_row[1]
        wo_count = wo_row[2]
        wo_line = wo_row[3]

        # 查询首站信息
        cursor.execute("""
            SELECT rc.op, lpc.routename, lpc.line
            FROM acc_line_partno_cfg lpc
            INNER JOIN acc_routing_cfg rc
                ON lpc.routename = rc.routename AND lpc.line = rc.line
            WHERE lpc.partno = :partno AND rc.status = '0'
        """, {'partno': partno})

        first_station_row = cursor.fetchone()
        if not first_station_row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到型号 {partno} 的路由信息'}), 404

        first_station = {
            'op': first_station_row[0],
            'routename': first_station_row[1],
            'line': first_station_row[2]
        }
        first_op = first_station_row[0]

        # 查询时间范围
        cursor.execute("""
            SELECT MIN(uh.STARTDT), MAX(uh.STARTDT)
            FROM acc_wo_workorder_detail awd
            INNER JOIN acc_unithistory uh ON awd.unitsn = uh.unitsn
            WHERE awd.wono = :wono
              AND awd.line = :wo_line
              AND uh.op = :first_op
              AND uh.result = 1
              AND uh.line = :wo_line
        """, {'wono': wono, 'wo_line': wo_line, 'first_op': first_op})

        time_row = cursor.fetchone()
        start_time = time_row[0] if time_row and time_row[0] else None
        end_time = time_row[1] if time_row and time_row[1] else None

        workorder_info = {
            'wono': wono,
            'partno': partno,
            'line': wo_line,
            'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S') if start_time else None,
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None,
            'wo_count': wo_count
        }

        # 查询未加入工单的产品（仅FG产品，status=2）
        # 使用子查询对每个产品只取最后一次经过首站的记录（解决返工导致重复的问题）
        missing_products = []
        if start_time and end_time:
            cursor.execute("""
                SELECT unitsn, pass_time, current_status FROM (
                    SELECT
                        last_pass.unitsn,
                        last_pass.pass_time,
                        us.status AS current_status
                    FROM (
                        -- 子查询：每个产品在首站的最后一条通过记录
                        SELECT uh.unitsn, MAX(uh.STARTDT) AS pass_time
                        FROM acc_unithistory uh
                        WHERE uh.op = :first_op
                          AND uh.result = 1
                          AND uh.line = :wo_line
                          AND uh.partno = :partno
                          AND uh.STARTDT BETWEEN :start_time AND :end_time
                        GROUP BY uh.unitsn
                    ) last_pass
                    LEFT JOIN acc_wo_workorder_detail awd
                        ON last_pass.unitsn = awd.unitsn AND awd.line = :wo_line
                    INNER JOIN acc_unitstatus us
                        ON last_pass.unitsn = us.unitsn AND us.line = :wo_line AND us.status = 2
                    WHERE awd.unitsn IS NULL
                    ORDER BY last_pass.pass_time
                ) WHERE ROWNUM <= 100
            """, {
                'first_op': first_op,
                'wo_line': wo_line,
                'partno': partno,
                'start_time': start_time,
                'end_time': end_time
            })

            for row in cursor.fetchall():
                current_status = row[2] if len(row) > 2 else None
                # 现在只会返回FG产品（status=2）
                missing_products.append({
                    'unitsn': row[0],
                    'createtime': row[1].strftime('%Y-%m-%d %H:%M:%S') if row[1] else None,
                    'partno': partno,
                    'current_status': current_status,
                    'status_desc': '已下线'
                })

        first_station_count = wo_count + len(missing_products)

        cursor.close()
        conn.close()

        summary = {
            'wo_count': wo_count,
            'first_station_count': first_station_count,
            'missing_count': len(missing_products)
        }

        return jsonify({
            'workorder_info': workorder_info,
            'first_station': first_station,
            'missing_products': missing_products,
            'summary': summary
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@workorder_bp.route('/api/add_missing_products', methods=['POST'])
def add_missing_products():
    """将未加入工单的产品插入到工单中"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        unitsn_list = data.get('unitsn_list', [])
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
        if not unitsn_list:
            return jsonify({'error': '请提供要插入的产品序列号列表'}), 400

        line_key = identify_line(wono)
        allowed, err = check_line_access(line_key)
        if not allowed:
            return err
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 查询工单基本信息
        cursor.execute("""
            SELECT wono, partno, line
            FROM acc_wo_workorder_detail
            WHERE wono = :wono AND ROWNUM = 1
        """, {'wono': wono})
        wo_row = cursor.fetchone()
        if not wo_row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到工单 {wono}'}), 404

        partno = wo_row[1]
        wo_line = wo_row[2]

        # 获取末站OP
        cursor.execute("""
            SELECT rc.op
            FROM acc_line_partno_cfg lpc
            INNER JOIN acc_routing_cfg rc
                ON lpc.routename = rc.routename AND lpc.line = rc.line
            WHERE lpc.partno = :partno AND lpc.line = :wo_line AND rc.status = '2'
        """, {'partno': partno, 'wo_line': wo_line})
        last_station_row = cursor.fetchone()
        last_station_op = last_station_row[0] if last_station_row else None

        # 获取模板记录
        cursor.execute("""
            SELECT wono, line, partno, rev, customersn, packingno,
                   isdelete, syncstatus, printcount, segment_code, retry
            FROM acc_wo_workorder_detail
            WHERE wono = :wono AND ROWNUM = 1
        """, {'wono': wono})
        template_row = cursor.fetchone()

        inserted_count = 0
        skipped_count = 0
        results = []

        for unitsn in unitsn_list:
            # 检查是否已存在
            cursor.execute("""
                SELECT COUNT(*) FROM acc_wo_workorder_detail
                WHERE wono = :wono AND unitsn = :unitsn
            """, {'wono': wono, 'unitsn': unitsn})
            if cursor.fetchone()[0] > 0:
                results.append({'unitsn': unitsn, 'action': 'skipped', 'reason': '已存在'})
                skipped_count += 1
                continue

            # 判断产品status（必须限制产线，因为同一产品在不同产线有不同状态）
            product_status = 1

            if last_station_op:
                # 检查是否通过末站（限制产线）
                cursor.execute("""
                    SELECT COUNT(*) FROM acc_unithistory
                    WHERE unitsn = :unitsn AND op = :last_op AND result = 1 AND line = :wo_line
                """, {'unitsn': unitsn, 'last_op': last_station_op, 'wo_line': wo_line})
                passed_last_station = cursor.fetchone()[0] > 0

                # 检查unitstatus状态（必须限制产线）
                cursor.execute("""
                    SELECT status FROM acc_unitstatus
                    WHERE unitsn = :unitsn AND line = :wo_line
                """, {'unitsn': unitsn, 'wo_line': wo_line})
                unitstatus_row = cursor.fetchone()
                unitstatus = unitstatus_row[0] if unitstatus_row else None

                # 通过末站且unitstatus=2才是完成状态
                if passed_last_station and str(unitstatus) == '2':
                    product_status = 2

            # 插入记录
            cursor.execute("""
                INSERT INTO acc_wo_workorder_detail
                (wono, line, partno, rev, unitsn, customersn, status, packingno,
                 isdelete, syncstatus, synctime, printcount, printtime, segment_code, retry, mtime)
                VALUES
                (:wono, :line, :partno, :rev, :unitsn, :customersn, :status, :packingno,
                 :isdelete, :syncstatus, NULL, :printcount, NULL, :segment_code, :retry, SYSDATE)
            """, {
                'wono': wono,
                'line': wo_line,
                'partno': partno,
                'rev': template_row[3] if template_row else 'A00',
                'unitsn': unitsn,
                'customersn': template_row[4] if template_row else None,
                'status': product_status,
                'packingno': None,
                'isdelete': 0,
                'syncstatus': 0,
                'printcount': 0,
                'segment_code': template_row[9] if template_row else '0',
                'retry': 0
            })

            inserted_count += 1
            results.append({
                'unitsn': unitsn,
                'action': 'inserted',
                'status': product_status,
                'status_desc': '完成' if product_status == 2 else '未完成'
            })

            # 记录操作日志
            log_workorder_op(
                unitsn=unitsn,
                linename=wo_line,
                wono=wono,
                partno=partno,
                product_status=product_status,
                operator=operator_id,
                result='SUCCESS',
                remark=f'插入缺失产品到工单,状态={product_status}'
            )

        conn.commit()
        cursor.close()
        conn.close()

        # 记录用户行为日志
        if inserted_count > 0:
            log_user('ADD_TO_WORKORDER', operator_id, f"添加产品到工单: {wono}",
                     wono=wono, partno=partno, line=wo_line,
                     inserted_count=inserted_count, skipped_count=skipped_count,
                     items=results)

        return jsonify({
            'success': True,
            'wono': wono,
            'inserted_count': inserted_count,
            'skipped_count': skipped_count,
            'results': results
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@workorder_bp.route('/api/check_product_status', methods=['POST'])
def check_product_status():
    """检查产品状态"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        unitsn_list = data.get('unitsn_list', [])

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400
        if not unitsn_list:
            return jsonify({'error': '请提供产品序列号列表'}), 400

        line_key = identify_line(wono)
        allowed, err = check_line_access(line_key)
        if not allowed:
            return err
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 获取工单信息
        cursor.execute("""
            SELECT partno, line FROM acc_wo_workorder_detail
            WHERE wono = :wono AND ROWNUM = 1
        """, {'wono': wono})
        wo_row = cursor.fetchone()
        if not wo_row:
            cursor.close()
            conn.close()
            return jsonify({'error': f'未找到工单 {wono}'}), 404

        partno = wo_row[0]
        wo_line = wo_row[1]

        # 获取末站OP
        cursor.execute("""
            SELECT rc.op
            FROM acc_line_partno_cfg lpc
            INNER JOIN acc_routing_cfg rc
                ON lpc.routename = rc.routename AND lpc.line = rc.line
            WHERE lpc.partno = :partno AND lpc.line = :wo_line AND rc.status = '2'
        """, {'partno': partno, 'wo_line': wo_line})
        last_station_row = cursor.fetchone()
        last_station_op = last_station_row[0] if last_station_row else None

        results = []
        for unitsn in unitsn_list:
            product_info = {
                'unitsn': unitsn,
                'passed_last_station': False,
                'unitstatus': None,
                'line': None,
                'final_status': 1,
                'final_status_desc': '未完成'
            }

            if last_station_op:
                cursor.execute("""
                    SELECT COUNT(*) FROM acc_unithistory
                    WHERE unitsn = :unitsn AND op = :last_op AND result = 1 AND line = :wo_line
                """, {'unitsn': unitsn, 'last_op': last_station_op, 'wo_line': wo_line})
                product_info['passed_last_station'] = cursor.fetchone()[0] > 0

                cursor.execute("""
                    SELECT status, line FROM acc_unitstatus
                    WHERE unitsn = :unitsn AND status = 2
                """, {'unitsn': unitsn})
                unitstatus_row = cursor.fetchone()
                if unitstatus_row:
                    product_info['unitstatus'] = unitstatus_row[0]
                    product_info['line'] = unitstatus_row[1]
                    product_info['final_status'] = 2
                    product_info['final_status_desc'] = '已下线(合格)'
                else:
                    cursor.execute("""
                        SELECT status, line FROM acc_unitstatus
                        WHERE unitsn = :unitsn
                    """, {'unitsn': unitsn})
                    other_row = cursor.fetchone()
                    if other_row:
                        product_info['unitstatus'] = other_row[0]
                        product_info['line'] = other_row[1]
                        product_info['final_status_desc'] = f'未下线(status={other_row[0]})'
                    else:
                        product_info['final_status_desc'] = '无状态记录'

            results.append(product_info)

        cursor.close()
        conn.close()

        return jsonify({
            'wono': wono,
            'partno': partno,
            'line': wo_line,
            'last_station_op': last_station_op,
            'products': results
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@workorder_bp.route('/api/get_workorder_quantity_info', methods=['POST'])
def get_workorder_quantity_info():
    """获取工单数量信息（计划数量、当前已加入数量）

    用于在加入产品前验证是否超出计划数量
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        line_key = identify_line(wono)
        allowed, err = check_line_access(line_key)
        if not allowed:
            return err

        # 1. 查询当前已加入工单的数量（从产线数据库）
        conn = get_connection(line_key)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM acc_wo_workorder_detail
            WHERE wono = :wono
        """, {'wono': wono})
        current_count = cursor.fetchone()[0] or 0

        cursor.close()
        conn.close()

        # 2. 查询工单计划数量（从iplant_web数据库）
        plan_quantity = None
        try:
            web_conn = get_iplant_web_connection()
            web_cursor = web_conn.cursor()

            web_cursor.execute("""
                SELECT QUANTITY FROM IP_WO_WORKORDER
                WHERE NO = :wono
            """, {'wono': wono})
            plan_row = web_cursor.fetchone()

            if plan_row:
                plan_quantity = plan_row[0]

            web_cursor.close()
            web_conn.close()
        except Exception as e:
            # 如果iplant_web连接失败，返回警告但不阻止操作
            return jsonify({
                'wono': wono,
                'current_count': current_count,
                'plan_quantity': None,
                'warning': f'无法获取计划数量: {str(e)}'
            })

        return jsonify({
            'wono': wono,
            'current_count': current_count,
            'plan_quantity': plan_quantity
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@workorder_bp.route('/api/validate_add_quantity', methods=['POST'])
def validate_add_quantity():
    """验证加入产品数量是否超出工单计划

    Args:
        wono: 工单号
        add_count: 要加入的产品数量

    Returns:
        valid: 是否允许加入
        message: 提示信息
        detail: 详细数量信息
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        add_count = data.get('add_count', 0)

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400
        if add_count <= 0:
            return jsonify({'error': '加入数量必须大于0'}), 400

        line_key = identify_line(wono)
        allowed, err = check_line_access(line_key)
        if not allowed:
            return err

        # 1. 查询当前已加入工单的数量
        conn = get_connection(line_key)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM acc_wo_workorder_detail
            WHERE wono = :wono
        """, {'wono': wono})
        current_count = cursor.fetchone()[0] or 0

        cursor.close()
        conn.close()

        # 2. 查询工单计划数量
        plan_quantity = None
        try:
            web_conn = get_iplant_web_connection()
            web_cursor = web_conn.cursor()

            web_cursor.execute("""
                SELECT QUANTITY FROM IP_WO_WORKORDER
                WHERE NO = :wono
            """, {'wono': wono})
            plan_row = web_cursor.fetchone()

            if plan_row:
                plan_quantity = plan_row[0]

            web_cursor.close()
            web_conn.close()
        except Exception as e:
            # 无法获取计划数量时，返回警告但允许继续操作
            return jsonify({
                'valid': True,
                'warning': f'无法获取计划数量，跳过验证: {str(e)}',
                'detail': {
                    'plan_quantity': None,
                    'current_count': current_count,
                    'add_count': add_count,
                    'total_after_add': current_count + add_count,
                    'exceed_count': None
                }
            })

        # 3. 验证数量
        if plan_quantity is None:
            # 工单在IP_WO_WORKORDER表中不存在，允许继续
            return jsonify({
                'valid': True,
                'warning': '工单计划数量未找到，跳过验证',
                'detail': {
                    'plan_quantity': None,
                    'current_count': current_count,
                    'add_count': add_count,
                    'total_after_add': current_count + add_count,
                    'exceed_count': None
                }
            })

        total_after_add = current_count + add_count
        exceed_count = total_after_add - plan_quantity

        if total_after_add > plan_quantity:
            return jsonify({
                'valid': False,
                'message': '超出工单计划数量',
                'detail': {
                    'plan_quantity': plan_quantity,
                    'current_count': current_count,
                    'add_count': add_count,
                    'total_after_add': total_after_add,
                    'exceed_count': exceed_count
                }
            })

        return jsonify({
            'valid': True,
            'message': '数量验证通过',
            'detail': {
                'plan_quantity': plan_quantity,
                'current_count': current_count,
                'add_count': add_count,
                'total_after_add': total_after_add,
                'exceed_count': 0,
                'remaining': plan_quantity - total_after_add
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

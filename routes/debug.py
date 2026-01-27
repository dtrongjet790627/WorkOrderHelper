# -*- coding: utf-8 -*-
"""调试接口路由"""

from flask import Blueprint, request, jsonify
from models.acc_db import get_connection
from utils.line_identifier import identify_line

debug_bp = Blueprint('debug', __name__)


@debug_bp.route('/api/debug/table_columns', methods=['POST'])
def debug_table_columns():
    """临时调试API：查询表结构"""
    try:
        data = request.json
        table_name = data.get('table_name', '').upper()
        wono = data.get('wono', 'MID25122204')

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT column_name, data_type
            FROM all_tab_columns
            WHERE table_name = :table_name
            ORDER BY column_id
        """, {'table_name': table_name})

        columns = [{'name': row[0], 'type': row[1]} for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        return jsonify({'table': table_name, 'columns': columns})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@debug_bp.route('/api/debug/sample_record', methods=['POST'])
def debug_sample_record():
    """调试：获取工单中一条完整记录"""
    try:
        data = request.json
        wono = data.get('wono', 'MID25122204')

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM acc_wo_workorder_detail
            WHERE wono = :wono AND ROWNUM = 1
        """, {'wono': wono})

        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if row:
            record = dict(zip(columns, [str(v) if v is not None else None for v in row]))
            return jsonify({'wono': wono, 'columns': columns, 'record': record})
        else:
            return jsonify({'error': f'工单 {wono} 无数据'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@debug_bp.route('/api/debug/check_routing', methods=['POST'])
def debug_check_routing():
    """调试：检查型号的路由配置"""
    try:
        data = request.json
        partno = data.get('partno', '')
        wono = data.get('wono', 'MID25122204')

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        results = {}

        # 查询 ACC_LINE_PARTNO_CFG
        cursor.execute("""
            SELECT PARTNO, ROUTENAME, LINE, ENABLE
            FROM ACC_LINE_PARTNO_CFG
            WHERE PARTNO = :partno
        """, {'partno': partno})
        partno_cfg = [{'partno': r[0], 'routename': r[1], 'line': r[2], 'enable': r[3]}
                      for r in cursor.fetchall()]
        results['acc_line_partno_cfg'] = partno_cfg

        # 查询路由配置
        if partno_cfg:
            routename = partno_cfg[0]['routename']
            line = partno_cfg[0]['line']

            cursor.execute("""
                SELECT ROUTENAME, LINE, OP, STATUS, DESCRIPTION, ENABLE
                FROM ACC_ROUTING_CFG
                WHERE ROUTENAME = :routename AND LINE = :line
                ORDER BY STATUS
            """, {'routename': routename, 'line': line})
            routing_cfg = [{'routename': r[0], 'line': r[1], 'op': r[2],
                           'status': r[3], 'description': r[4], 'enable': r[5]}
                          for r in cursor.fetchall()]
            results['acc_routing_cfg'] = routing_cfg

            # 首站
            cursor.execute("""
                SELECT OP, STATUS, DESCRIPTION FROM ACC_ROUTING_CFG
                WHERE ROUTENAME = :routename AND LINE = :line AND STATUS = '0'
            """, {'routename': routename, 'line': line})
            first_row = cursor.fetchone()
            results['first_station'] = {'op': first_row[0], 'status': first_row[1],
                                        'description': first_row[2]} if first_row else None

            # 末站
            cursor.execute("""
                SELECT OP, STATUS, DESCRIPTION FROM ACC_ROUTING_CFG
                WHERE ROUTENAME = :routename AND LINE = :line AND STATUS = '2'
            """, {'routename': routename, 'line': line})
            last_row = cursor.fetchone()
            results['last_station'] = {'op': last_row[0], 'status': last_row[1],
                                       'description': last_row[2]} if last_row else None

        cursor.close()
        conn.close()

        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

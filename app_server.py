#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ACC工单管理系统 - ERP收货处理
"""

import os
import sys

# PyInstaller 打包后路径处理 - 在所有导入之前设置
if getattr(sys, 'frozen', False):
    # 打包后，exe所在目录
    _BASE_DIR = os.path.dirname(sys.executable)
    # 调试输出到文件
    with open(os.path.join(_BASE_DIR, 'startup_debug.log'), 'w', encoding='utf-8') as f:
        f.write(f'frozen: True\n')
        f.write(f'executable: {sys.executable}\n')
        f.write(f'BASE_DIR: {_BASE_DIR}\n')
        f.write(f'cwd: {os.getcwd()}\n')
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from flask import Flask, render_template, request, jsonify, redirect, url_for
import cx_Oracle
import pymssql
import pandas as pd
from io import BytesIO
import subprocess
import re
from datetime import datetime
import paramiko  # SSH库，用于连接EAI服务器读取日志

# 工单查询模块（韩大师提供）可选导入
# 当前API已内置查询逻辑，如需使用模块化版本可取消注释
# from workorder_query import get_workorder_time_range, get_first_station_op, get_products_not_in_workorder, get_workorder_summary

# 创建Flask应用
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(_BASE_DIR, 'templates')
    static_folder = os.path.join(_BASE_DIR, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    # 记录Flask初始化
    with open(os.path.join(_BASE_DIR, 'startup_debug.log'), 'a', encoding='utf-8') as f:
        f.write(f'template_folder: {template_folder}\n')
        f.write(f'static_folder: {static_folder}\n')
        f.write(f'Flask app created\n')
else:
    app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['TEMPLATES_AUTO_RELOAD'] = True  # 禁用模板缓存
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 禁用静态文件缓存

# 为静态文件添加禁用缓存的响应头
@app.after_request
def add_header(response):
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 禁用静态文件缓存

# 注册蓝图（routes目录下的模块）
from routes import register_blueprints
register_blueprints(app)

# ACC数据库配置 (Oracle)
DB_CONFIG = {
    'host': '172.17.10.165',
    'port': 1521,
    'service_name': 'orcl.ecdag.com'
}

# ERP数据库配置 (SQL Server) - 按产线区分
ERP_DB_CONFIG = {
    'line1': {  # 电控一线、总成线
        'server': '172.17.10.183',
        'user': 'sa',
        'password': 'Hangqu123',
        'database': 'AIS20250623094458'
    },
    'line2': {  # 电控二线
        'server': '172.17.10.198',
        'user': 'sa',
        'password': 'Hangqu123',
        'database': 'AIS20251031172112'
    }
}

# 产线用户配置
LINE_CONFIG = {
    'dpepp1': {'user': 'iplant_dpepp1', 'password': 'acc', 'name': '电控一线', 'prefixes': ['SMT', 'MID', 'EPP']},
    'smt2': {'user': 'iplant_smt2', 'password': 'acc', 'name': '电控二线', 'prefixes': ['SMT-2', 'MID-2']},
    'dpeps1': {'user': 'iplant_dpeps1', 'password': 'acc', 'name': '总成DP产线', 'prefixes': ['EPS', 'IPA']},
    'ceps1': {'user': 'iplant_ceps1', 'password': 'acc', 'name': '总成C产线', 'prefixes': ['C']}
}

def identify_line(wono):
    """根据工单号识别产线"""
    wono_upper = wono.upper()
    # 电控二线 - 有'-'号
    if '-2' in wono_upper and wono_upper[4:6] == '22':
        return 'smt2'
    # 总成DP产线
    if wono_upper.startswith('EPS') or wono_upper.startswith('IPA'):
        return 'dpeps1'
    # 电控一线
    if wono_upper.startswith(('SMT', 'MID', 'EPP')):
        return 'dpepp1'
    # 默认
    return 'dpepp1'

def get_connection(line_key):
    """获取ACC数据库连接(Oracle)"""
    from utils.logger import log_db
    config = LINE_CONFIG[line_key]
    dsn = cx_Oracle.makedsn(DB_CONFIG['host'], DB_CONFIG['port'], service_name=DB_CONFIG['service_name'])
    try:
        conn = cx_Oracle.connect(user=config['user'], password=config['password'], dsn=dsn)
        log_db('CONNECT', 'ACC', f"连接成功: {config['user']}@{DB_CONFIG['host']}", line=line_key)
        return conn
    except Exception as e:
        log_db('CONNECT', 'ACC', f"连接失败: {str(e)}", line=line_key, error=True)
        raise

def identify_erp_line(wono):
    """根据工单号识别ERP数据库（电控二线用198，其他用183）"""
    wono_upper = wono.upper()
    # 电控二线：工单号含'-2'且第5-6位是'22'
    if '-2' in wono_upper:
        return 'line2'
    # 其他产线（电控一线、总成线）
    return 'line1'

def get_erp_connection(wono):
    """根据工单号获取对应的ERP数据库连接(SQL Server)"""
    erp_line = identify_erp_line(wono)
    config = ERP_DB_CONFIG[erp_line]
    return pymssql.connect(
        server=config['server'],
        user=config['user'],
        password=config['password'],
        database=config['database']
    )


# ============================================
#   系统日志
# ============================================
from utils.logger import log_api, log_system, log_user, log_error, log_startup, get_log_files, read_log_file
from datetime import datetime as dt_now
import time

# 记录系统启动
log_startup()

# API请求日志中间件
@app.before_request
def log_request_start():
    """记录请求开始时间"""
    request.start_time = time.time()

@app.after_request
def log_request_end(response):
    """记录API请求日志"""
    # 跳过静态资源
    if request.path.startswith('/static/'):
        return response

    duration = round((time.time() - getattr(request, 'start_time', time.time())) * 1000)
    operator = request.cookies.get('operator_id', '-')

    # 记录API日志
    log_api(
        method=request.method,
        path=request.path,
        status_code=response.status_code,
        duration_ms=duration,
        operator=operator,
        ip=request.remote_addr
    )

    return response


# ============================================
#   License授权检查
# ============================================
from utils.license import get_cached_license_status, get_license_info, clear_license_cache, LICENSE_FILE

# 不需要License检查的路径
LICENSE_EXEMPT_PATHS = [
    '/license',
    '/api/activate_license',
    '/static/',
    '/favicon.ico'
]

@app.before_request
def check_license():
    """请求前检查License授权"""
    # 跳过豁免路径
    for path in LICENSE_EXEMPT_PATHS:
        if request.path.startswith(path):
            return None

    # 检查License
    status = get_cached_license_status()
    if not status['valid']:
        return redirect(url_for('license_page'))

    return None


@app.route('/license')
def license_page():
    """授权验证页面"""
    status = get_cached_license_status()
    return render_template('license_expired.html',
                         license_info=status.get('license_info'),
                         message=status.get('message'))


@app.route('/api/activate_license', methods=['POST'])
def activate_license():
    """激活License"""
    try:
        data = request.json
        license_code = data.get('license_code', '').strip()

        if not license_code:
            return jsonify({'success': False, 'message': '请输入授权码'})

        # 验证授权码格式（尝试解码）
        import base64
        import json as json_lib
        try:
            decoded = base64.b64decode(license_code).decode('utf-8')
            lic_data = json_lib.loads(decoded)

            # 检查必要字段
            if 'expire_date' not in lic_data or 'signature' not in lic_data:
                return jsonify({'success': False, 'message': '授权码格式无效'})

            # 检查是否过期
            # 过期日期当天仍然有效，第二天才算过期
            from datetime import datetime
            expire_date = datetime.strptime(lic_data['expire_date'], '%Y-%m-%d')
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            expire_date_end = expire_date.replace(hour=23, minute=59, second=59)
            if today > expire_date_end:
                return jsonify({'success': False, 'message': f"授权码已过期 ({lic_data['expire_date']})"})

        except Exception as e:
            return jsonify({'success': False, 'message': '授权码无效，无法解析'})

        # 保存License文件
        with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
            f.write(license_code)

        # 清除缓存
        clear_license_cache()

        # 再次验证
        from utils.license import check_license as verify_license
        result = verify_license()
        if result['valid']:
            info = result['license_info']
            return jsonify({
                'success': True,
                'message': f"授权成功！有效期至 {info['expire_date']}，剩余 {info['days_remaining']} 天"
            })
        else:
            return jsonify({'success': False, 'message': result['message']})

    except Exception as e:
        return jsonify({'success': False, 'message': f'激活失败: {str(e)}'})


@app.route('/api/license_info')
def api_license_info():
    """获取License信息API"""
    return jsonify(get_license_info())


@app.route('/')
def index():
    return render_template('index_hulu.html', lines=LINE_CONFIG)

@app.route('/api/query_workorder', methods=['POST'])
def query_workorder():
    """查询工单完成情况（含未加入工单产品和未打包产品）"""
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        line_key = identify_line(wono)
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
        cursor.execute("""
            SELECT
                ph.packid,
                COUNT(*) AS qty,
                pi.currquantity,
                pi.packsize,
                pi.status,
                TO_CHAR(pi.lastupdatetime, 'YYYY-MM-DD HH24:MI:SS') AS lastupdate
            FROM pack_history ph
            JOIN pack_info pi ON ph.packid = pi.packid
            WHERE EXISTS (
                SELECT 1 FROM acc_wo_workorder_detail awd
                WHERE awd.unitsn = ph.unitsn
                AND awd.wono = :wono
                AND awd.status = 2
                AND awd.line = ph.line
            )
            GROUP BY ph.packid, pi.currquantity, pi.packsize, pi.status, pi.lastupdatetime
            ORDER BY ph.packid
        """, {'wono': wono})

        pack_list = []
        for row in cursor.fetchall():
            pack_list.append({
                'packid': row[0],
                'actual_qty': row[1],
                'info_qty': row[2],
                'packsize': row[3],
                'status': '已封包' if row[4] == 2 else '生产中' if row[4] == 0 else str(row[4]),
                'lastupdate': row[5],
                'other_wonos': []  # 初始化其它工单列表
            })

        # 对于info_qty > actual_qty的批次，查询其它工单信息
        for pack in pack_list:
            if pack['info_qty'] and pack['actual_qty'] and pack['info_qty'] > pack['actual_qty']:
                # 查询该批次中包含的所有工单及数量（排除当前工单）
                cursor.execute("""
                    SELECT awd.wono, COUNT(*) AS qty
                    FROM acc_wo_workorder_detail awd
                    WHERE awd.unitsn IN (
                        SELECT ph.unitsn FROM pack_history ph
                        WHERE ph.packid = :packid AND ph.line = :wo_line
                    )
                    AND awd.line = :wo_line
                    AND awd.wono != :wono
                    GROUP BY awd.wono
                    ORDER BY awd.wono
                """, {'packid': pack['packid'], 'wo_line': wo_line, 'wono': wono})

                other_wonos = []
                for wo_row in cursor.fetchall():
                    other_wonos.append({
                        'wono': wo_row[0],
                        'qty': wo_row[1]
                    })
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

        # ==================== 未加入工单产品：默认不查询（耗时操作） ====================
        # 由于acc_unithistory表数据量大，查询耗时，改为用户手动触发
        missing_products = []
        missing_summary = {'wo_count': wo_count, 'first_station_count': wo_count, 'missing_count': 0, 'need_query': True}
        first_station_info = None

        # 只查询首站信息（快速）
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

        # ==================== 查询未打包产品（优化：NOT EXISTS） ====================
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

        return jsonify({
            'workorder': workorder_info,
            'packs': pack_list,
            'erp': erp_list,
            'erp_total': erp_total,
            'pack_total': sum(p['actual_qty'] for p in pack_list),
            # 未加入工单产品
            'missing_products': missing_products,
            'missing_summary': missing_summary,
            'first_station': first_station_info,
            # 未打包产品
            'unpacked_products': unpacked_products,
            'unpacked_count': len(unpacked_products)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload_erp', methods=['POST'])
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

        wono = str(df.iloc[0, 4])  # 源单编号
        partno = str(df.iloc[0, 6])  # 物料编码

        # 按批号汇总 - 使用完成数量(Col13)
        batch_data = {}
        for idx, row in df.iterrows():
            batch = str(row.iloc[19])
            qty = int(row.iloc[13])  # 完成数量
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

@app.route('/api/sync_data', methods=['POST'])
def sync_data():
    """同步数据 - 执行收货调整"""
    try:
        data = request.json
        wono = data.get('wono')
        erp_batches = data.get('erp_batches', [])  # [{'packid': 'xxx', 'qty': 100}, ...]

        if not wono or not erp_batches:
            return jsonify({'error': '参数不完整'}), 400

        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        results = []

        # 1. 查询当前数据库中各批次数量
        erp_dict = {b['packid']: b['qty'] for b in erp_batches}

        cursor.execute("""
            SELECT packid, COUNT(*) AS qty
            FROM epr_report_work_history
            WHERE wono = :wono
            GROUP BY packid
        """, {'wono': wono})

        db_batches = {row[0]: row[1] for row in cursor.fetchall()}

        # 2. 对比并删除多余记录
        for packid, db_qty in db_batches.items():
            erp_qty = erp_dict.get(packid, 0)
            if db_qty > erp_qty:
                delete_count = db_qty - erp_qty
                # 删除epr_report_work_history
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

        # 3. 同步pack_history
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

        # 4. 更新pack_info
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
            results.append(f"pack_info: 批次{packid} {curr_qty}→{actual_qty}")

        conn.commit()

        # 5. 查询ACC_WO中缺失的记录
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

@app.route('/api/add_missing', methods=['POST'])
def add_missing():
    """补充缺失记录到pack_history"""
    try:
        data = request.json
        wono = data.get('wono')

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

        # 找目标批次（倒序第二个数量为0的批次）
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

        # 插入缺失记录
        cursor.execute("""
            INSERT INTO pack_history (packid, unitsn, packbarcode, packdate, lastupdatetime, line, stn, trwsn, customerpackid, customerpartno)
            SELECT
                :target_packid,
                awd.unitsn,
                awd.unitsn,
                SYSDATE, SYSDATE,
                :line,
                :stn,
                NULL, NULL, NULL
            FROM acc_wo_workorder_detail awd
            WHERE awd.wono = :wono AND awd.status = 2
            AND NOT EXISTS (
                SELECT 1 FROM pack_history ph
                WHERE ph.unitsn = awd.unitsn AND ph.line = awd.line
            )
        """, {'target_packid': target_packid, 'line': line, 'stn': ref_stn, 'wono': wono})

        inserted_count = cursor.rowcount

        if inserted_count > 0:
            # 更新pack_info
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

        return jsonify({
            'success': True,
            'inserted_count': inserted_count,
            'target_packid': target_packid,
            'message': f'成功插入{inserted_count}条记录到批次{target_packid}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/query_missing_products', methods=['POST'])
def query_missing_products():
    """查询未加入工单的产品

    查找在首站过站但未加入工单的产品序列号

    逻辑：
    1. 从acc_wo_workorder_detail获取工单所有主码(unitsn)和line
    2. 用这些主码在acc_unithistory中找首站+result=1的时间段
    3. 在此时间段内，找同一line、同一首站OP、result=1的所有产品
    4. 对比找出不在acc_wo_workorder_detail工单内的产品
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        # 识别产线并获取数据库连接
        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 1. 查询工单基本信息（产品型号、数量、line）
        cursor.execute("""
            SELECT
                wono,
                partno,
                COUNT(*) AS wo_count,
                line
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

        # 2. 查询该型号的首站信息（从acc_line_partno_cfg和acc_routing_cfg获取）
        cursor.execute("""
            SELECT rc.op, lpc.routename, lpc.line
            FROM acc_line_partno_cfg lpc
            INNER JOIN acc_routing_cfg rc
                ON lpc.routename = rc.routename
                AND lpc.line = rc.line
            WHERE lpc.partno = :partno
              AND rc.status = '0'
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

        # 3. 高性能优化：从工单表JOIN查询时间范围（工单数据量小，查询快）
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

        # 4. 高性能优化：使用LEFT JOIN + ROWNUM限制返回数量
        missing_products = []
        if start_time and end_time:
            cursor.execute("""
                SELECT unitsn, pass_time FROM (
                    SELECT uh.unitsn, uh.STARTDT AS pass_time
                    FROM acc_unithistory uh
                    LEFT JOIN acc_wo_workorder_detail awd
                        ON uh.unitsn = awd.unitsn AND awd.wono = :wono AND awd.line = :wo_line
                    WHERE uh.op = :first_op
                      AND uh.result = 1
                      AND uh.line = :wo_line
                      AND uh.partno = :partno
                      AND uh.STARTDT BETWEEN :start_time AND :end_time
                      AND awd.unitsn IS NULL
                    ORDER BY uh.STARTDT
                ) WHERE ROWNUM <= 100
            """, {
                'first_op': first_op,
                'wo_line': wo_line,
                'partno': partno,
                'start_time': start_time,
                'end_time': end_time,
                'wono': wono
            })

            for row in cursor.fetchall():
                missing_products.append({
                    'unitsn': row[0],
                    'createtime': row[1].strftime('%Y-%m-%d %H:%M:%S') if row[1] else None,
                    'partno': partno
                })

        # 5. 估算首站PASS总数（避免大表COUNT）
        first_station_count = wo_count + len(missing_products)

        cursor.close()
        conn.close()

        # 6. 构建返回结果
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


@app.route('/api/add_missing_products', methods=['POST'])
def add_missing_products():
    """
    将未加入工单的产品插入到工单中

    逻辑：
    1. 获取工单基本信息和末站OP
    2. 获取工单中一条记录作为模板（获取其它字段值）
    3. 对每个待插入的产品判断status：
       - 如果产品在acc_unithistory中通过末站(result=1)
       - 且acc_unitstatus.status=2
       - 则status=2（完成），否则status=1（未完成）
    4. 插入到acc_wo_workorder_detail表
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        unitsn_list = data.get('unitsn_list', [])

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400
        if not unitsn_list:
            return jsonify({'error': '请提供要插入的产品序列号列表'}), 400

        # 识别产线并获取数据库连接
        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        # 1. 查询工单基本信息
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

        # 2. 获取末站OP（status=2）
        cursor.execute("""
            SELECT rc.op
            FROM acc_line_partno_cfg lpc
            INNER JOIN acc_routing_cfg rc
                ON lpc.routename = rc.routename
                AND lpc.line = rc.line
            WHERE lpc.partno = :partno
              AND lpc.line = :wo_line
              AND rc.status = '2'
        """, {'partno': partno, 'wo_line': wo_line})
        last_station_row = cursor.fetchone()
        last_station_op = last_station_row[0] if last_station_row else None

        # 3. 获取工单中一条记录作为模板（获取REV等字段值）
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

            # 4. 判断产品status
            product_status = 1  # 默认未完成

            if last_station_op:
                # 检查产品是否通过末站（acc_unithistory中op=末站, result=1）
                cursor.execute("""
                    SELECT COUNT(*) FROM acc_unithistory
                    WHERE unitsn = :unitsn
                      AND op = :last_op
                      AND result = 1
                      AND line = :wo_line
                """, {'unitsn': unitsn, 'last_op': last_station_op, 'wo_line': wo_line})
                passed_last_station = cursor.fetchone()[0] > 0

                # 检查acc_unitstatus表中status是否为2
                cursor.execute("""
                    SELECT status FROM acc_unitstatus
                    WHERE unitsn = :unitsn AND line = :wo_line
                """, {'unitsn': unitsn, 'wo_line': wo_line})
                unitstatus_row = cursor.fetchone()
                unitstatus = unitstatus_row[0] if unitstatus_row else None

                # 如果通过末站且unitstatus=2，则status=2
                if passed_last_station and unitstatus == 2:
                    product_status = 2

            # 5. 插入到acc_wo_workorder_detail（使用正确的字段）
            # 模板字段顺序: wono(0), line(1), partno(2), rev(3), customersn(4), packingno(5),
            #              isdelete(6), syncstatus(7), printcount(8), segment_code(9), retry(10)
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
                'packingno': None,  # 新插入的产品未打包
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

        # 提交事务
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'wono': wono,
            'inserted_count': inserted_count,
            'skipped_count': skipped_count,
            'results': results
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/check_product_status', methods=['POST'])
def check_product_status():
    """
    检查产品状态（是否完成）

    用于在插入前预览产品的status值
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        unitsn_list = data.get('unitsn_list', [])

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400
        if not unitsn_list:
            return jsonify({'error': '请提供产品序列号列表'}), 400

        # 识别产线并获取数据库连接
        line_key = identify_line(wono)
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
                'line': None,  # 产品在acc_unitstatus中的产线
                'final_status': 1,
                'final_status_desc': '未完成'
            }

            if last_station_op:
                # 检查是否通过末站
                cursor.execute("""
                    SELECT COUNT(*) FROM acc_unithistory
                    WHERE unitsn = :unitsn AND op = :last_op
                      AND result = 1 AND line = :wo_line
                """, {'unitsn': unitsn, 'last_op': last_station_op, 'wo_line': wo_line})
                product_info['passed_last_station'] = cursor.fetchone()[0] > 0

                # 检查acc_unitstatus（只要status=2就是成功下线）
                # 注意：acc_unitstatus表的line格式可能与工单表不同，所以不比较line
                cursor.execute("""
                    SELECT status, line FROM acc_unitstatus
                    WHERE unitsn = :unitsn AND status = 2
                """, {'unitsn': unitsn})
                unitstatus_row = cursor.fetchone()
                if unitstatus_row:
                    product_info['unitstatus'] = unitstatus_row[0]
                    product_info['line'] = unitstatus_row[1]
                    # 只要status=2就是成功下线（合格品）
                    product_info['final_status'] = 2
                    product_info['final_status_desc'] = '已下线(合格)'
                else:
                    # 没有status=2的记录，检查是否有其他状态
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


@app.route('/api/debug/table_columns', methods=['POST'])
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


@app.route('/api/debug/sample_record', methods=['POST'])
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


@app.route('/api/debug/check_routing', methods=['POST'])
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

        # 1. 查询 ACC_LINE_PARTNO_CFG 中的记录
        cursor.execute("""
            SELECT PARTNO, ROUTENAME, LINE, ENABLE
            FROM ACC_LINE_PARTNO_CFG
            WHERE PARTNO = :partno
        """, {'partno': partno})
        partno_cfg = [{'partno': r[0], 'routename': r[1], 'line': r[2], 'enable': r[3]}
                      for r in cursor.fetchall()]
        results['acc_line_partno_cfg'] = partno_cfg

        # 2. 如果有路由配置，查询 ACC_ROUTING_CFG
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

            # 3. 首站 (status=0)
            cursor.execute("""
                SELECT OP, STATUS, DESCRIPTION FROM ACC_ROUTING_CFG
                WHERE ROUTENAME = :routename AND LINE = :line AND STATUS = '0'
            """, {'routename': routename, 'line': line})
            first_row = cursor.fetchone()
            results['first_station'] = {'op': first_row[0], 'status': first_row[1],
                                        'description': first_row[2]} if first_row else None

            # 4. 末站 (status=2)
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


@app.route('/api/query_unpacked_products', methods=['POST'])
def query_unpacked_products():
    """
    查询完工但未打包的产品

    逻辑：
    1. 查询acc_wo_workorder_detail中status=2且packingno为空的产品
    2. 这些产品已完工但未加入任何包装
    """
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

        # 查询完工但未打包的产品列表（优化：NOT EXISTS代替NOT IN）
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


@app.route('/api/get_pack_batches', methods=['POST'])
def get_pack_batches():
    """
    获取可用的目标批次（currquantity=0的批次）和参考批次
    """
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

        # 查询可用目标批次（currquantity=0，按时间倒序）
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

        # 查询参考批次（status=2且currquantity>0，最近一个）
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




@app.route('/api/generate_pack_id', methods=['POST'])
def generate_pack_id():
    """
    自动生成新批次号并创建pack_info记录
    格式: YYYYMMDD + 产线代码(S/M/A) + 7位序列号
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()

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

        # 从产线名获取产线代码
        line_code = 'S' if 'SMT' in wo_line.upper() else ('M' if 'MID' in wo_line.upper() else 'A')

        # 查询该型号最后一个批次 (Oracle 11g兼容语法)
        cursor.execute("""
            SELECT packid FROM (
                SELECT packid FROM pack_info
                WHERE prodtype = :partno
                ORDER BY lastupdate DESC NULLS LAST
            ) WHERE ROWNUM = 1
        """, {'partno': partno})

        row = cursor.fetchone()
        last_pack_id = row[0] if row else None

        # 生成新批次号
        today = datetime.now().strftime('%Y%m%d')

        if last_pack_id is None:
            new_pack_id = f"{today}{line_code}0000001"
        else:
            last_date = last_pack_id[:8]
            last_line_code = last_pack_id[8:9]
            if last_date != today:
                new_pack_id = f"{today}{line_code}0000001"
            else:
                try:
                    last_seq = int(last_pack_id[9:])
                    new_pack_id = f"{today}{last_line_code}{last_seq + 1:07d}"
                except ValueError:
                    new_pack_id = f"{today}{line_code}0000001"

        # 获取参考批次的stn等信息
        cursor.execute("""
            SELECT stn, drag, generatorname, customerpackid, customerpartno
            FROM (
                SELECT stn, drag, generatorname, customerpackid, customerpartno,
                       ROW_NUMBER() OVER (ORDER BY lastupdate DESC NULLS LAST) AS rn
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

        # 创建新的pack_info记录 (修复: 添加packsize和line字段，移除createtime)
        cursor.execute("""
            INSERT INTO pack_info
            (packid, prodtype, packsize, currquantity, status, lastupdate, lastupdatetime,
             line, stn, drag, generatorname, customerpackid, customerpartno)
            VALUES
            (:packid, :prodtype, 300, 0, 0, SYSDATE, SYSDATE,
             :line, :stn, :drag, :generatorname, :customerpackid, :customerpartno)
        """, {
            'packid': new_pack_id,
            'prodtype': partno,
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

        return jsonify({
            'success': True,
            'pack_id': new_pack_id,
            'partno': partno,
            'line': wo_line
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/execute_packing', methods=['POST'])
def execute_packing():
    """
    执行补打包操作
    1. 插入pack_history
    2. 更新pack_info
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()
        target_packid = data.get('target_packid', '').strip()
        unitsn_list = data.get('unitsn_list', [])
        reference_packid = data.get('reference_packid', '').strip()

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

        # 获取参考批次的stn等信息
        cursor.execute("""
            SELECT stn, drag, generatorname, customerpackid, customerpartno
            FROM pack_info WHERE packid = :packid
        """, {'packid': reference_packid if reference_packid else target_packid})
        ref_row = cursor.fetchone()

        ref_stn = ref_row[0] if ref_row else None
        ref_drag = ref_row[1] if ref_row else None
        ref_generatorname = ref_row[2] if ref_row else None
        ref_customerpackid = ref_row[3] if ref_row else None
        ref_customerpartno = ref_row[4] if ref_row else None

        inserted_count = 0
        skipped_count = 0
        results = []

        for unitsn in unitsn_list:
            # 检查是否已在pack_history中
            cursor.execute("""
                SELECT COUNT(*) FROM pack_history
                WHERE unitsn = :unitsn AND line = :line
            """, {'unitsn': unitsn, 'line': wo_line})
            if cursor.fetchone()[0] > 0:
                results.append({'unitsn': unitsn, 'action': 'skipped', 'reason': '已存在于pack_history'})
                skipped_count += 1
                continue

            # 插入pack_history
            cursor.execute("""
                INSERT INTO pack_history
                (packid, unitsn, packbarcode, packdate, lastupdatetime, line, stn, trwsn, customerpackid, customerpartno)
                VALUES
                (:packid, :unitsn, :packbarcode, SYSDATE, SYSDATE, :line, :stn, NULL, :customerpackid, :customerpartno)
            """, {
                'packid': target_packid,
                'unitsn': unitsn,
                'packbarcode': unitsn,
                'line': wo_line,
                'stn': ref_stn,
                'customerpackid': ref_customerpackid,
                'customerpartno': ref_customerpartno
            })

            inserted_count += 1
            results.append({'unitsn': unitsn, 'action': 'inserted', 'packid': target_packid})

        # 更新pack_info的数量
        if inserted_count > 0:
            # 获取当前批次在pack_history中的总数量
            cursor.execute("""
                SELECT COUNT(*) FROM pack_history WHERE packid = :packid
            """, {'packid': target_packid})
            new_qty = cursor.fetchone()[0]

            # 更新pack_info
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
                'stn': ref_stn,
                'drag': ref_drag,
                'generatorname': ref_generatorname,
                'customerpackid': ref_customerpackid,
                'customerpartno': ref_customerpartno,
                'packid': target_packid
            })

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'wono': wono,
            'target_packid': target_packid,
            'inserted_count': inserted_count,
            'skipped_count': skipped_count,
            'results': results
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/query_erp_packs', methods=['POST'])
def query_erp_packs():
    """
    从ERP数据库直接查询工单的批次汇总
    表: T_PRD_MORPT (生产汇报主表) + T_PRD_MORPTENTRY (明细表)
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        # 连接ERP数据库（根据工单号自动选择183或198）
        erp_conn = get_erp_connection(wono)
        erp_cursor = erp_conn.cursor()

        # 查询ERP生产汇报数据，按批号汇总（使用FQUAQTY完成数量字段）
        erp_cursor.execute("""
            SELECT
                e.FLOT_TEXT AS packid,
                SUM(e.FQUAQTY) AS qty
            FROM T_PRD_MORPTENTRY e
            JOIN T_PRD_MORPT h ON e.FID = h.FID
            WHERE e.FMOBILLNO = %s
              AND h.FDOCUMENTSTATUS = 'C'
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


@app.route('/api/compare_acc_erp', methods=['POST'])
def compare_acc_erp():
    """
    对比ACC数据库与ERP数据库的工单包装数据
    """
    try:
        data = request.json
        wono = data.get('wono', '').strip()

        if not wono:
            return jsonify({'error': '请输入工单号'}), 400

        # ========== 1. 查询ERP数据（根据工单号自动选择数据库） ==========
        erp_conn = get_erp_connection(wono)
        erp_cursor = erp_conn.cursor()

        # 先查询ERP收货记录数（不分组，同批次多次收货算多条）
        erp_cursor.execute("""
            SELECT COUNT(*) AS batch_count
            FROM T_PRD_MORPTENTRY e
            JOIN T_PRD_MORPT h ON e.FID = h.FID
            WHERE e.FMOBILLNO = %s
              AND h.FDOCUMENTSTATUS = 'C'
        """, (wono,))
        erp_batch_count_row = erp_cursor.fetchone()
        erp_batch_count = int(erp_batch_count_row[0]) if erp_batch_count_row else 0

        # 查询ERP每条收货记录（不分组，同批次多次收货分开显示，按单据ID区分）
        erp_cursor.execute("""
            SELECT
                e.FLOT_TEXT AS packid,
                e.FQUAQTY AS qty,
                h.FBILLNO AS bill_no
            FROM T_PRD_MORPTENTRY e
            JOIN T_PRD_MORPT h ON e.FID = h.FID
            WHERE e.FMOBILLNO = %s
              AND h.FDOCUMENTSTATUS = 'C'
            ORDER BY e.FLOT_TEXT, h.FBILLNO
        """, (wono,))

        erp_records = []  # 保存每条ERP记录
        erp_dict = {}     # 按批次汇总用于计算
        erp_total = 0
        for row in erp_cursor.fetchall():
            packid = row[0]
            qty = int(row[1]) if row[1] else 0
            bill_no = row[2] if len(row) > 2 else ''
            erp_records.append({'packid': packid, 'qty': qty, 'bill_no': bill_no})
            erp_dict[packid] = erp_dict.get(packid, 0) + qty
            erp_total += qty

        erp_cursor.close()
        erp_conn.close()

        # ========== 2. 查询ACC数据 ==========
        line_key = identify_line(wono)
        acc_conn = get_connection(line_key)
        acc_cursor = acc_conn.cursor()

        # 查询pack_history按批次汇总
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
            ORDER BY ph.packid
        """, {'wono': wono})

        acc_dict = {}
        acc_total = 0
        for row in acc_cursor.fetchall():
            packid = row[0]
            qty = row[1]
            acc_dict[packid] = qty
            acc_total += qty

        acc_cursor.close()
        acc_conn.close()

        # ========== 3. 对比分析 ==========
        # 获取所有唯一批次号
        all_packids = sorted(set(list(erp_dict.keys()) + list(acc_dict.keys())))

        comparison = []
        processed_packids = set()  # 记录已处理的批次，用于ACC数量只显示一次

        # 先处理ERP中的记录（展开显示每条）
        for erp_record in erp_records:
            packid = erp_record['packid']
            erp_qty = erp_record['qty']
            bill_no = erp_record.get('bill_no', '')

            # ACC数量：同一批次只在第一条显示
            if packid not in processed_packids:
                acc_qty = acc_dict.get(packid, 0)
                processed_packids.add(packid)
                # 计算该批次的总差异
                total_erp_qty = erp_dict.get(packid, 0)
                diff = acc_qty - total_erp_qty
                status = 'match' if diff == 0 else ('acc_more' if diff > 0 else 'erp_more')
            else:
                acc_qty = None  # 同批次后续记录不重复显示ACC数量
                diff = None
                status = 'continuation'  # 标记为同批次的续行

            comparison.append({
                'packid': packid,
                'erp_qty': erp_qty,
                'acc_qty': acc_qty,
                'diff': diff,
                'status': status,
                'bill_no': bill_no  # 添加单据号以区分同批次不同收货
            })

        # 再处理只在ACC中有、ERP中没有的批次
        for packid in all_packids:
            if packid not in processed_packids:
                acc_qty = acc_dict.get(packid, 0)
                comparison.append({
                    'packid': packid,
                    'erp_qty': 0,
                    'acc_qty': acc_qty,
                    'diff': acc_qty,
                    'status': 'acc_only'
                })

        # 统计（只统计主记录，不统计续行）
        main_records = [c for c in comparison if c['status'] != 'continuation']
        match_count = sum(1 for c in main_records if c['status'] == 'match')
        mismatch_count = len(main_records) - match_count

        return jsonify({
            'success': True,
            'wono': wono,
            'erp_total': erp_total,
            'erp_batch_count': erp_batch_count,
            'acc_total': acc_total,
            'diff_total': acc_total - erp_total,
            'comparison': comparison,
            'summary': {
                'total_batches': len(comparison),
                'match_count': match_count,
                'mismatch_count': mismatch_count
            }
        })

    except Exception as e:
        return jsonify({'error': f'对比失败: {str(e)}'}), 500


# EAI服务器配置
EAI_SERVER = {
    'host': '172.17.10.163',
    'port': 2200,
    'user': 'root',
    'password': 'Hangqu123',  # SSH密码
    'log_path': '/var/eai/logs/'
}

# EAI日志文件映射（根据产线）- 使用Linux正斜杠路径
EAI_LOG_FILES = {
    'dpeps1': 'FLOW_DP-EPS\IPA MES报工接口.log',           # DP EPS/DP IPA
    'smt2': 'FLOW_SMT\MID-Line2MES报工接口.log',           # SMT Line2/MID Line2
    'dpepp1': 'FLOW_DP-SMT\MID\EPP MES报工接口.log',      # DP SMT/DP MID/DP EPP
}


def should_include_log_line(line):
    """
    判断日志行是否应该包含在结果中

    只保留有用信息：
    1. 触发器获取到的数据（db trigger get data）
    2. ERP响应（kingdee response）- 包含成功/失败状态
    3. 流程执行失败（run failed）
    4. 流程执行成功（run success）
    5. 错误日志（run error / ErrorLog）

    过滤无用信息：
    - action [...] start / end
    - triggered（没有数据的触发通知）
    - start listen
    - kingdee request（请求信息通常不需要展示）
    """
    line_lower = line.lower()

    # ===== 必须保留的关键信息 =====
    # 触发器获取到数据
    if 'db trigger get data' in line_lower:
        return True

    # ERP响应 - 只保留成功的（失败的在run error中已有详细信息）
    if 'kingdee response' in line_lower:
        # 只保留成功的响应
        if '"issuccess":true' in line_lower or '"issuccess": true' in line_lower:
            return True
        # 失败的响应不保留，因为run error已包含完整信息
        return False

    # 执行错误（包含详细错误信息）
    if 'run error' in line_lower:
        return True

    # run success/run failed 都不需要，客户只关注待报工和报工结果
    if 'run failed' in line_lower or 'run success' in line_lower:
        return False

    # ===== 过滤无用信息 =====
    # action start/end
    if 'action [' in line_lower and ('] start' in line_lower or '] end' in line_lower):
        return False

    # 触发通知（没有数据）
    if 'triggered' in line_lower:
        return False

    # 开始监听
    if 'start listen' in line_lower:
        return False

    # ERP请求 - 保留用于提取工单信息（后续与响应合并）
    if 'kingdee request' in line_lower:
        return True

    # 其他INFO日志默认过滤
    return False


def parse_eai_log_line(line):
    """
    解析EAI日志行，提取关键信息

    只处理有用的日志类型：
    1. 触发器数据（db trigger get data）- 展示所有待处理记录
    2. ERP响应（kingdee response）- 提取成功/失败状态和错误信息
    3. 执行错误（run error）- 提取详细错误信息
    4. 流程状态（run failed/success）
    """
    import json as json_module

    result = {
        'time': None,
        'level': 'INFO',
        'wono': None,
        'batch': None,
        'qty': None,
        'partno': None,
        'line_name': None,
        'status': None,
        'schb_no': None,
        'error_msg': None,
        'raw': None,
        'log_type': None,
        'record_count': None,
        'all_records': None  # 存储所有触发器记录（用于前端展示）
    }

    # 提取日志级别
    level_match = re.search(r'^\[(INFO|ERRO|WARN|ERROR)\]', line)
    if level_match:
        level = level_match.group(1)
        if level in ('ERRO', 'ERROR'):
            result['level'] = 'ERROR'
        elif level == 'WARN':
            result['level'] = 'WARN'
        else:
            result['level'] = 'INFO'

    # 提取时间戳
    time_match = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
    if time_match:
        result['time'] = time_match.group(1)

    # ========== 1. 处理触发器数据（展示所有记录） ==========
    if 'db trigger get data' in line:
        result['log_type'] = 'trigger'
        result['level'] = 'INFO'
        result['status'] = 'pending'  # 待报工状态
        json_match = re.search(r'db trigger get data:\s*(\[.*)', line)
        if json_match:
            json_str = json_match.group(1)
            try:
                # 尝试解析JSON（可能被截断）
                try:
                    records = json_module.loads(json_str)
                except json_module.JSONDecodeError:
                    # 修复截断的JSON
                    last_brace = json_str.rfind('}')
                    if last_brace > 0:
                        fixed_json = json_str[:last_brace+1] + ']'
                        records = json_module.loads(fixed_json)
                    else:
                        records = []

                if records and isinstance(records, list):
                    result['record_count'] = len(records)
                    # 存储所有记录供前端展示
                    result['all_records'] = records

                    # 提取第一条记录的关键信息（用于表格主列显示）
                    first_record = records[0]
                    result['wono'] = first_record.get('WONO')
                    result['batch'] = first_record.get('PACKID')
                    result['qty'] = first_record.get('CNT')
                    result['partno'] = first_record.get('PARTNO')
                    result['line_name'] = first_record.get('LINE')

                    # 详情只显示条数，具体信息已在字段列中显示
                    if len(records) == 1:
                        result['raw'] = '待报工'
                    else:
                        result['raw'] = f'待报工({len(records)}条)'
            except Exception as e:
                result['raw'] = f'触发报工(解析失败: {str(e)[:50]})'
        else:
            result['raw'] = '触发报工'
        return result

    # ========== 2. 处理ERP请求（提取工单信息） ==========
    if 'kingdee request' in line.lower():
        result['log_type'] = 'request'
        result['level'] = 'INFO'
        # 注意：JSON可能是转义格式（\"而不是"），需要同时处理两种情况
        # 提取工单号 FMoBillNo（支持转义和非转义格式）
        wono_match = re.search(r'\\?"FMoBillNo\\?"\s*:\s*\\?"([^"\\]+)\\?"', line)
        if wono_match:
            result['wono'] = wono_match.group(1)
        # 提取批次号 FLot.FNumber（支持转义格式）
        batch_match = re.search(r'\\?"FLot\\?"\s*:\s*\{?\s*\\?"FNumber\\?"\s*:\s*\\?"([^"\\]+)\\?"', line)
        if batch_match:
            result['batch'] = batch_match.group(1)
        # 提取型号 FMaterialId.FNumber（支持转义格式）
        partno_match = re.search(r'\\?"FMaterialId\\?"\s*:\s*\{?\s*\\?"FNumber\\?"\s*:\s*\\?"([^"\\]+)\\?"', line)
        if partno_match:
            result['partno'] = partno_match.group(1)
        # 提取数量 FFinishQty（支持转义格式）
        qty_match = re.search(r'\\?"FFinishQty\\?"\s*:\s*(\d+)', line)
        if qty_match:
            result['qty'] = qty_match.group(1)
        result['raw'] = '发送报工请求'
        return result

    # ========== 3. 处理ERP响应 ==========
    if 'kingdee response' in line.lower():
        result['log_type'] = 'response'
        # 提取SCHB单号
        schb_match = re.search(r'"Number"\s*:\s*"(SCHB\d+)"', line)
        if schb_match:
            result['schb_no'] = schb_match.group(1)

        # 判断成功/失败
        if '"IsSuccess":true' in line or '"IsSuccess": true' in line:
            result['status'] = 'success'
            result['level'] = 'SUCCESS'
            result['raw'] = '<span class="text-success">报工成功</span>'
        elif '"IsSuccess":false' in line or '"IsSuccess": false' in line:
            result['status'] = 'failed'
            result['level'] = 'ERROR'
            msg_match = re.search(r'"Message"\s*:\s*"([^"]+)"', line)
            if msg_match:
                result['error_msg'] = msg_match.group(1)
                result['raw'] = f'<span class="text-danger">{result["error_msg"]}</span>'
            else:
                result['raw'] = '<span class="text-danger">报工失败</span>'
        return result

    # ========== 3. 处理执行错误（run error，包含详细错误信息） ==========
    if 'run error' in line.lower():
        result['log_type'] = 'error'
        result['status'] = 'failed'
        result['level'] = 'ERROR'

        # 日志格式: {"data":"{\"CNT\":\"290\",...,\"WONO\":\"MID-225122901\"}","errorMsg":"...\"Message\":\"错误信息\"..."}
        # 注意：日志文件中 \" 是两个字符（反斜杠+双引号）

        # 1. 提取data中的字段（使用转义格式匹配）
        # 匹配 \"WONO\":\"xxx\"
        wono_match = re.search(r'\\"WONO\\":\s*\\"([^"\\]+)\\"', line)
        if wono_match:
            result['wono'] = wono_match.group(1)

        batch_match = re.search(r'\\"PACKID\\":\s*\\"([^"\\]+)\\"', line)
        if batch_match:
            result['batch'] = batch_match.group(1)

        qty_match = re.search(r'\\"CNT\\":\s*\\"(\d+)\\"', line)
        if qty_match:
            result['qty'] = qty_match.group(1)

        partno_match = re.search(r'\\"PARTNO\\":\s*\\"([^"\\]+)\\"', line)
        if partno_match:
            result['partno'] = partno_match.group(1)

        line_match = re.search(r'\\"LINE\\":\s*\\"([^"\\]+)\\"', line)
        if line_match:
            result['line_name'] = line_match.group(1)

        # 2. 提取错误信息（Message字段）
        # 格式: \"Message\":\"生产汇报单对应的生产订单...\"
        msg_match = re.search(r'\\"Message\\":\s*\\"([^"\\]+)\\"', line)
        if msg_match:
            result['error_msg'] = msg_match.group(1)

        # 生成详情显示（只显示关键错误信息）
        if result['error_msg']:
            result['raw'] = f'<span class="text-danger">{result["error_msg"]}</span>'
        else:
            result['raw'] = '<span class="text-danger">执行错误</span>'
        return result

    # ========== 4. 处理流程执行状态 ==========
    if 'run failed' in line.lower():
        result['log_type'] = 'error'
        result['status'] = 'failed'
        result['level'] = 'ERROR'
        cost_match = re.search(r'cost\s+(\d+)\s*ms', line)
        if cost_match:
            result['raw'] = f'<span class="text-danger"><b>流程失败</b></span> (耗时{cost_match.group(1)}ms)'
        else:
            result['raw'] = '<span class="text-danger"><b>流程失败</b></span>'
        return result

    if 'run success' in line.lower():
        result['log_type'] = 'success'
        result['status'] = 'success'
        result['level'] = 'SUCCESS'
        cost_match = re.search(r'cost\s+(\d+)\s*ms', line)
        if cost_match:
            result['raw'] = f'<span class="text-success"><b>流程成功</b></span> (耗时{cost_match.group(1)}ms)'
        else:
            result['raw'] = '<span class="text-success"><b>流程成功</b></span>'
        return result

    # ========== 5. 兜底：其他错误日志 ==========
    if result['level'] == 'ERROR':
        result['log_type'] = 'error'
        # 尝试提取关键信息
        wono_match = re.search(r'"(?:WONO|FMoBillNo)"\s*:\s*"([^"]+)"', line)
        if wono_match:
            result['wono'] = wono_match.group(1)
        batch_match = re.search(r'"(?:PACKID|FNumber)"\s*:\s*"([^"]+)"', line)
        if batch_match:
            result['batch'] = batch_match.group(1)
        # 简化显示
        simplified = re.sub(r'^\[.*?\]\[.*?\]\[.*?\]\[.*?\]\s*>+\s*', '', line.strip())
        result['raw'] = f'<span class="text-danger">{simplified[:150]}</span>'

    return result


def deduplicate_error_logs(logs):
    """
    去重连续相同的失败日志
    相同工单+相同批次+相同错误信息的连续失败只保留第一条
    """
    if not logs:
        return logs

    result = []
    seen_errors = {}  # key: (wono, batch, error_msg), value: first_time

    for log in logs:
        # 成功的日志始终保留
        if log.get('status') == 'success' or log.get('level') == 'SUCCESS':
            # 成功后清除该工单的错误记录（因为已经修复了）
            key_prefix = (log.get('wono'), log.get('batch'))
            keys_to_remove = [k for k in seen_errors if k[:2] == key_prefix]
            for k in keys_to_remove:
                del seen_errors[k]
            result.append(log)
        elif log.get('status') == 'failed' or log.get('level') == 'ERROR':
            # 失败的日志需要去重
            key = (log.get('wono'), log.get('batch'), log.get('error_msg') or log.get('raw'))
            if key not in seen_errors:
                seen_errors[key] = log.get('time')
                result.append(log)
            # 如果已存在相同错误，跳过
        else:
            # 其他类型（如trigger、request）保留
            result.append(log)

    return result


def ssh_execute_command(command, timeout=30):
    """
    使用paramiko执行SSH命令
    返回: (success, output, error_msg)
    """
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=EAI_SERVER['host'],
            port=EAI_SERVER['port'],
            username=EAI_SERVER['user'],
            password=EAI_SERVER['password'],
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False
        )

        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        output = stdout.read().decode('utf-8', errors='replace')
        error = stderr.read().decode('utf-8', errors='replace')

        return True, output, error
    except paramiko.AuthenticationException:
        return False, '', 'SSH认证失败：用户名或密码错误'
    except paramiko.SSHException as e:
        return False, '', f'SSH连接错误: {str(e)}'
    except Exception as e:
        return False, '', f'连接失败: {str(e)}'
    finally:
        if ssh:
            ssh.close()


@app.route('/api/eai_logs', methods=['POST'])
def get_eai_logs():
    """
    获取EAI接口日志
    参数:
        wono: 工单号（可选，用于过滤）
        line_key: 产线标识（可选，dpepp1/smt2/dpeps1）
        limit: 返回条数限制（默认100）
        level: 日志级别过滤（可选，ERROR/WARN/SUCCESS/INFO）
    """
    try:
        data = request.json or {}
        wono = data.get('wono', '').strip()
        line_key = data.get('line_key', '').strip()
        limit = int(data.get('limit', 100))
        level_filter = data.get('level', '').upper()

        # 根据工单号自动识别产线
        if wono and not line_key:
            line_key = identify_line(wono)

        # 如果没有指定产线，默认查询所有产线
        log_files_to_query = []
        if line_key and line_key in EAI_LOG_FILES:
            log_files_to_query = [(line_key, EAI_LOG_FILES[line_key])]
        else:
            log_files_to_query = list(EAI_LOG_FILES.items())

        all_logs = []

        for lk, log_file in log_files_to_query:
            # 构建远程日志文件路径
            remote_path = EAI_SERVER['log_path'] + log_file

            # 构建SSH命令（在远程服务器上执行）
            if wono:
                # 如果指定工单号，使用grep过滤
                cmd = f"grep -i '{wono}' '{remote_path}' 2>/dev/null | tail -n {limit}"
            else:
                # 否则读取最后N行
                cmd = f"tail -n {limit} '{remote_path}' 2>/dev/null"

            try:
                # 使用paramiko执行SSH命令
                success, output, error_msg = ssh_execute_command(cmd, timeout=30)

                if success and output:
                    lines = output.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            # 先判断是否是有用的日志行
                            if not should_include_log_line(line):
                                continue

                            parsed = parse_eai_log_line(line)
                            # 跳过没有有效内容的日志
                            if not parsed.get('raw') and not parsed.get('schb_no') and not parsed.get('error_msg'):
                                continue

                            parsed['line_key'] = lk
                            parsed['log_file'] = log_file

                            # 级别过滤
                            if level_filter and parsed['level'] != level_filter:
                                continue

                            all_logs.append(parsed)
                elif not success:
                    # SSH连接失败
                    all_logs.append({
                        'level': 'ERROR',
                        'raw': f'[{lk}] {error_msg}',
                        'line_key': lk,
                        'log_file': log_file
                    })
                elif error_msg:
                    # 命令执行有警告
                    all_logs.append({
                        'level': 'WARN',
                        'raw': f'[{lk}] 日志读取警告: {error_msg[:200]}',
                        'line_key': lk,
                        'log_file': log_file
                    })

            except Exception as e:
                all_logs.append({
                    'level': 'ERROR',
                    'raw': f'[{lk}] 读取失败: {str(e)[:100]}',
                    'line_key': lk,
                    'log_file': log_file
                })

        # 处理日志：展开触发器多条记录、合并请求和响应
        requests = []  # 请求日志（用于与响应合并）
        responses = []  # 响应日志（成功的）
        triggers = []  # 触发器原始数据（备用，当请求匹配失败时使用）
        processed_logs = []
        error_trigger_groups = set()  # 记录已有error响应的trigger组
        batch_to_schb = {}  # 批次号 -> 汇报单号的映射

        # 第一遍：收集所有请求和响应，建立批次号到汇报单号的映射
        for log in all_logs:
            if log.get('log_type') == 'request':
                requests.append(log)
            elif log.get('log_type') == 'response' and log.get('status') == 'success':
                responses.append(log)

        # 建立 request -> response 的关联，提取 batch -> schb_no 映射
        used_resp_indices = set()
        for req in requests:
            req_time = req.get('time', '')
            req_line = req.get('line_key', '')
            req_batch = req.get('batch', '')

            if not req_batch:
                continue

            # 查找匹配的成功响应（同一产线，时间在请求之后10秒内）
            for idx, resp in enumerate(responses):
                if idx in used_resp_indices:
                    continue
                resp_time = resp.get('time', '')
                resp_line = resp.get('line_key', '')
                if resp_line != req_line:
                    continue
                if req_time and resp_time and req_time <= resp_time:
                    try:
                        req_dt = datetime.strptime(req_time, '%Y-%m-%d %H:%M:%S')
                        resp_dt = datetime.strptime(resp_time, '%Y-%m-%d %H:%M:%S')
                        time_diff = (resp_dt - req_dt).total_seconds()
                        if 0 <= time_diff <= 10:
                            # 找到匹配的响应，建立映射
                            schb_no = resp.get('schb_no')
                            if schb_no:
                                batch_to_schb[req_batch] = schb_no
                            used_resp_indices.add(idx)
                            break
                    except:
                        pass

        # 第二遍：处理所有日志
        for log in all_logs:
            if log.get('log_type') == 'request':
                # 请求日志不直接展示
                pass
            elif log.get('log_type') == 'response' and log.get('status') == 'failed':
                # 失败响应：丢弃（run error中有详细信息）
                pass
            elif log.get('log_type') == 'trigger' and log.get('all_records'):
                # 保存触发器原始数据（用于备用查询）
                triggers.append(log)

                # 触发器数据：展开成多条记录
                # 同一组的第一条显示完整信息，后续记录省略时间/级别/产线
                records = log.get('all_records', [])
                base_time = log.get('time', '')
                line_key = log.get('line_key', '')
                log_file = log.get('log_file', '')

                # 如果有工单号过滤条件，只展开包含该工单号的记录
                # 修复：按工单号查询时只显示相关记录，避免rowspan错乱
                if wono:
                    filtered_records = [r for r in records if r.get('WONO', '').upper() == wono.upper()]
                    # 如果过滤后没有记录，跳过这个trigger（不应该发生，因为grep已过滤）
                    if not filtered_records:
                        continue
                    records = filtered_records

                total_count = len(records)

                # 检查这组记录中有多少已成功报工
                success_count = 0
                for record in records:
                    packid = record.get('PACKID')
                    if packid and packid in batch_to_schb:
                        success_count += 1

                for idx, record in enumerate(records):
                    is_first = (idx == 0)
                    packid = record.get('PACKID')
                    # 查找该批次的汇报单号
                    record_schb_no = batch_to_schb.get(packid) if packid else None
                    # 根据是否有汇报单号确定状态
                    if record_schb_no:
                        record_status = 'success'
                    else:
                        record_status = 'pending'

                    expanded_log = {
                        'time': base_time if is_first else '',  # 只有第一条显示时间
                        'level': 'INFO' if is_first else '',     # 只有第一条显示级别
                        'log_type': 'trigger',
                        'status': record_status if is_first else '',  # 只有第一条显示状态
                        'wono': record.get('WONO'),
                        'batch': packid,
                        'partno': record.get('PARTNO'),
                        'qty': record.get('CNT'),
                        'line_name': record.get('LINE'),
                        'line_key': line_key if is_first else '',  # 只有第一条显示产线
                        'log_file': log_file,
                        'schb_no': record_schb_no,
                        'raw': '',
                        'is_group_first': is_first,  # 标记是否是组内第一条
                        'group_id': base_time,  # 用时间作为组标识
                        'group_order': idx  # 保存原始顺序索引，用于排序时保持JSON数组顺序
                    }
                    # 设置raw显示
                    if is_first:
                        if success_count == total_count:
                            expanded_log['raw'] = f'<span class="text-success">报工成功({total_count}条)</span>'
                        elif success_count > 0:
                            expanded_log['raw'] = f'<span class="text-warning">部分成功({success_count}/{total_count})</span>'
                        else:
                            expanded_log['raw'] = f'待报工({total_count}条)'
                    processed_logs.append(expanded_log)
            else:
                # 对于error日志，尝试关联到最近的trigger组
                if log.get('log_type') == 'error' and log.get('status') == 'failed':
                    log_time = log.get('time', '')
                    log_wono = log.get('wono', '')
                    best_trigger = None

                    # 查找匹配的trigger（优先匹配工单号+时间，其次只匹配时间）
                    for trigger in triggers:
                        trigger_time = trigger.get('time', '')
                        if trigger_time and log_time and trigger_time <= log_time:
                            # 检查时间差（60秒内）
                            try:
                                trigger_dt = datetime.strptime(trigger_time, '%Y-%m-%d %H:%M:%S')
                                log_dt = datetime.strptime(log_time, '%Y-%m-%d %H:%M:%S')
                                time_diff = (log_dt - trigger_dt).total_seconds()
                                if time_diff <= 60:
                                    # 优先匹配包含相同工单号的trigger
                                    if log_wono:
                                        trigger_records = trigger.get('all_records', [])
                                        for rec in trigger_records:
                                            if rec.get('WONO') == log_wono:
                                                best_trigger = trigger
                                                break
                                    if not best_trigger:
                                        # 如果没找到匹配工单号的，用时间最近的
                                        if best_trigger is None or trigger_time > best_trigger.get('time', ''):
                                            best_trigger = trigger
                            except:
                                pass

                    # 设置group_id关联到trigger组
                    if best_trigger:
                        trigger_group_id = best_trigger.get('time', '')
                        log['group_id'] = trigger_group_id
                        log['group_order'] = 999  # 放在组内最后
                        # 标记这个trigger组已被处理（有error响应）
                        error_trigger_groups.add(trigger_group_id)

                processed_logs.append(log)

        # 成功响应的信息已通过batch_to_schb合并到trigger记录中，不需要单独显示
        # 只保留trigger和error日志
        merged_logs = []

        for log in processed_logs:
            if log.get('log_type') == 'response' and log.get('status') == 'success':
                # 成功响应不单独显示，信息已通过batch_to_schb合并到trigger记录
                continue

            merged_logs.append(log)

        all_logs = merged_logs

        # 对于已有error响应的trigger组，更新trigger记录的状态为失败
        # 注意：成功状态已在展开trigger时通过batch_to_schb精确匹配设置
        for log in all_logs:
            if log.get('log_type') == 'trigger':
                group_id = log.get('group_id')
                if group_id in error_trigger_groups:
                    # 这个trigger组有error响应，将待报工状态改为失败
                    if log.get('status') == 'pending':
                        log['status'] = 'failed'
                        # 只有当第一条显示"待报工"时才改为"报工失败"
                        # 如果已经显示了"部分成功"或其他统计信息，保留原有显示
                        if log.get('is_group_first') and '待报工' in (log.get('raw') or ''):
                            log['raw'] = f'<span class="text-danger">报工失败</span>'

        # 按时间倒序排列，同组记录保持原顺序
        # 使用group_id（触发时间）作为主排序键，确保同组记录在一起
        # 使用group_order保持组内记录的原始JSON数组顺序
        def sort_key(x):
            group_id = x.get('group_id') or x.get('time') or ''
            group_order = x.get('group_order', 0)  # 原始索引，idx=0的记录排在组内第一位
            return (group_id, -group_order)  # 取负值，reverse=True后idx=0的排在最前

        all_logs.sort(key=sort_key, reverse=True)

        # 去重连续相同的失败日志
        all_logs = deduplicate_error_logs(all_logs)

        # 限制返回条数
        all_logs = all_logs[:limit]

        # 统计
        summary = {
            'total': len(all_logs),
            'success': sum(1 for log in all_logs if log.get('status') == 'success'),
            'failed': sum(1 for log in all_logs if log.get('status') == 'failed'),
            'pending': sum(1 for log in all_logs if log.get('status') == 'pending'),
            'error': sum(1 for log in all_logs if log.get('level') == 'ERROR'),
            'warn': sum(1 for log in all_logs if log.get('level') == 'WARN')
        }

        return jsonify({
            'success': True,
            'logs': all_logs,
            'summary': summary,
            'query_info': {
                'wono': wono or '全部',
                'line_key': line_key or '全部产线',
                'limit': limit,
                'level_filter': level_filter or '全部'
            }
        })

    except Exception as e:
        return jsonify({'error': f'查询EAI日志失败: {str(e)}'}), 500


@app.route('/api/eai_logs/recent_errors', methods=['GET'])
def get_eai_recent_errors():
    """
    获取最近的EAI接口错误日志（快捷接口）
    """
    try:
        all_errors = []

        for lk, log_file in EAI_LOG_FILES.items():
            remote_path = EAI_SERVER['log_path'] + log_file

            # 使用grep过滤错误日志
            cmd = f"grep -iE '(ERROR|失败|FAIL)' '{remote_path}' 2>/dev/null | tail -n 20"

            try:
                success, output, error_msg = ssh_execute_command(cmd, timeout=30)

                if success and output:
                    lines = output.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            parsed = parse_eai_log_line(line)
                            parsed['line_key'] = lk
                            all_errors.append(parsed)

            except Exception:
                pass  # 静默处理错误

        # 按时间倒序
        all_errors.sort(key=lambda x: x.get('time', '') or '', reverse=True)

        return jsonify({
            'success': True,
            'errors': all_errors[:50],
            'count': len(all_errors)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eai_logs/test', methods=['GET'])
def test_eai_connection():
    """测试EAI服务器SSH连接"""
    try:
        # 测试SSH连接
        cmd = "ls -la /var/eai/logs/ | grep -i 'MES' | grep -v '.gz' | head -5"
        success, output, error_msg = ssh_execute_command(cmd, timeout=15)

        if success:
            # 尝试读取一个日志文件
            log_file = EAI_LOG_FILES.get('smt2', '')
            remote_path = EAI_SERVER['log_path'] + log_file
            cmd2 = f"tail -n 3 '{remote_path}' 2>&1"
            success2, output2, error_msg2 = ssh_execute_command(cmd2, timeout=15)

            return jsonify({
                'ssh_connection': 'OK',
                'log_files_found': output.strip().split('\n') if output else [],
                'test_log_file': log_file,
                'test_command': cmd2,
                'test_read_success': success2,
                'test_read_output': output2[:500] if output2 else '',
                'test_read_error': error_msg2[:200] if error_msg2 else ''
            })
        else:
            return jsonify({
                'ssh_connection': 'FAILED',
                'error': error_msg
            }), 500
    except Exception as e:
        return jsonify({
            'ssh_connection': 'ERROR',
            'exception': str(e)
        }), 500


# ============================================
#   系统日志查看API
# ============================================
@app.route('/api/logs/files')
def get_logs_files():
    """获取日志文件列表"""
    try:
        files = get_log_files()
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/logs/read')
def read_logs():
    """读取日志内容"""
    try:
        # 支持file和filename两个参数名
        filename = request.args.get('filename') or request.args.get('file', 'system.log')
        lines = int(request.args.get('lines', 500))
        search = request.args.get('search', '')
        level = request.args.get('level', '')

        # 安全检查：防止路径遍历
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': '非法文件名'})

        content = read_log_file(filename, lines, search if search else None, level if level else None)

        # 获取文件大小信息
        from utils.logger import LOG_DIR
        filepath = os.path.join(LOG_DIR, filename)
        size_str = '-'
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    size_str = f"{size:.1f}{unit}"
                    break
                size /= 1024

        return jsonify({
            'lines': content,
            'count': len(content),
            'size_str': size_str,
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)

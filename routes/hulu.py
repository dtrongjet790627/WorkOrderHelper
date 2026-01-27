# -*- coding: utf-8 -*-
"""HULU系统相关路由"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import json as json_lib
from config.database import HULU_REDIS_HOST, HULU_REDIS_PORT
from models.acc_db import get_connection
from utils.line_identifier import identify_line
from utils.permission import check_user_permission
from utils.operation_log import log_hulu_sync_batch

# Redis库（可选）
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

hulu_bp = Blueprint('hulu', __name__)


def get_acc_products_for_sync(wono):
    """从ACC获取产品数据用于同步"""
    try:
        line_key = identify_line(wono)
        conn = get_connection(line_key)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT awd.unitsn, awd.partno, awd.line, awd.status, awd.packingno, awd.mtime
            FROM acc_wo_workorder_detail awd
            WHERE awd.wono = :wono
            ORDER BY awd.unitsn
        """, {'wono': wono})

        products = []
        for row in cursor.fetchall():
            products.append({
                'unitsn': row[0],
                'partno': row[1],
                'line': row[2],
                'status': row[3],
                'packingno': row[4],
                'mtime': str(row[5]) if row[5] else None
            })

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'products': products,
                'total': len(products)
            }
        }

    except Exception as e:
        print(f"ACC数据查询错误: {e}")
        return {'success': False, 'message': 'ACC数据查询失败，请稍后重试'}


def fetch_hulu_data(wono):
    """从HULU系统获取工单数据"""
    if not REDIS_AVAILABLE:
        return {
            'order_info': {
                'work_order': wono,
                'type': '-',
                'plan_qty': '-',
                'status': 'Redis模块未安装',
                'start_time': '-',
                'end_time': '-'
            },
            'production': {
                'finished': 0,
                'planned': 0,
                'in_progress': 0,
                'scrapped': 0
            },
            'info_list': []
        }

    try:
        r = redis.Redis(host=HULU_REDIS_HOST, port=HULU_REDIS_PORT, decode_responses=True, socket_timeout=5)

        result = {
            'order_info': {},
            'production': {},
            'info_list': []
        }

        prefix_to_keys = {
            'SMT': ['workorderconfig:SMT Line2', 'workorderconfig:DP SMT1'],
            'MID': ['workorderconfig:MID Line2', 'workorderconfig:DP MID1'],
            'EPP': ['workorderconfig:DP EPP1'],
            'DP': ['workorderconfig:DP EPP1', 'workorderconfig:DP MID1', 'workorderconfig:DP SMT1'],
            'EPS': ['workorderconfig:DP EPP1'],
        }

        wono_prefix = wono.split('-')[0].upper() if '-' in wono else wono[:3].upper()
        priority_keys = prefix_to_keys.get(wono_prefix, [])

        if not priority_keys:
            priority_keys = r.keys('workorderconfig:*')
        else:
            all_keys = r.keys('workorderconfig:*')
            other_keys = [k for k in all_keys if k not in priority_keys]
            priority_keys = priority_keys + other_keys

        found_data = None
        found_line = None

        for key in priority_keys:
            try:
                if r.hexists(key, wono):
                    value = r.hget(key, wono)
                    if value:
                        try:
                            found_data = json_lib.loads(value)
                            found_line = key.replace('workorderconfig:', '')
                            break
                        except:
                            pass
            except:
                continue

        if found_data:
            status_map = {'1': '待生产', '2': '生产中', '3': '生产中', '4': '已完成'}
            status_val = found_data.get('status', '')
            status_text = status_map.get(str(status_val), str(status_val))

            def format_time(t):
                if not t or t.startswith('0001-01-01'):
                    return '-'
                return t.replace('T', ' ').split('+')[0][:19] if 'T' in t else t

            result['order_info'] = {
                'work_order': found_data.get('work_order_no', wono),
                'type': '生产工单',
                'plan_qty': found_data.get('plan_count', '-'),
                'status': status_text,
                'start_time': format_time(found_data.get('plan_start_time', '')),
                'end_time': format_time(found_data.get('plan_end_time', '')),
                'line': found_data.get('line', found_line),
                'part_no': found_data.get('part_no', '-'),
                'rev': found_data.get('rev', '-'),
                'last_update': format_time(found_data.get('last_update_time', ''))
            }
            result['production'] = {
                'finished': found_data.get('finish_count', 0),
                'planned': found_data.get('plan_count', 0),
                'in_progress': found_data.get('wip_count', 0),
                'scrapped': found_data.get('scrap_count', 0)
            }

            units = found_data.get('units', [])
            unit_status_map = {'1': '在制', '2': '完成', '0': '待处理'}

            result['finished_list'] = []
            result['wip_list'] = []

            for unit in units:
                unit_data = {
                    'barcode': unit.get('unit_sn', '-'),
                    'station': unit.get('stn', '-'),
                    'status': unit_status_map.get(str(unit.get('status', '')), str(unit.get('status', '-'))),
                    'time': format_time(unit.get('ctime', ''))
                }

                unit_status = str(unit.get('status', ''))
                if unit_status == '2':
                    result['finished_list'].append(unit_data)
                elif unit_status == '1':
                    result['wip_list'].append(unit_data)
                else:
                    result['wip_list'].append(unit_data)

            result['info_list'] = result['wip_list'] + result['finished_list']

        if not result['order_info']:
            result['order_info'] = {
                'work_order': wono,
                'type': '生产工单',
                'plan_qty': '-',
                'status': 'HULU中无数据',
                'start_time': '-',
                'end_time': '-'
            }
            result['production'] = {
                'finished': 0,
                'planned': 0,
                'in_progress': 0,
                'scrapped': 0
            }

        return result

    except redis.ConnectionError as e:
        return {
            'order_info': {
                'work_order': wono,
                'type': '-',
                'plan_qty': '-',
                'status': 'Redis连接失败',
                'start_time': '-',
                'end_time': '-'
            },
            'production': {
                'finished': 0,
                'planned': 0,
                'in_progress': 0,
                'scrapped': 0
            },
            'info_list': []
        }
    except redis.ResponseError as e:
        error_msg = str(e)
        if 'MISCONF' in error_msg:
            return {
                'order_info': {
                    'work_order': wono,
                    'type': '-',
                    'plan_qty': '-',
                    'status': 'HULU暂时不可用',
                    'start_time': '-',
                    'end_time': '-'
                },
                'production': {
                    'finished': 0,
                    'planned': 0,
                    'in_progress': 0,
                    'scrapped': 0
                },
                'info_list': [],
                'error_type': 'REDIS_READONLY',
                'user_tip': '请稍后重试，如持续出现请联系运维'
            }
        raise Exception(f"HULU数据读取失败，请联系运维检查")
    except Exception as e:
        raise Exception(f"HULU数据读取失败，请联系运维检查")


@hulu_bp.route('/api/sync_to_hulu', methods=['POST'])
def sync_to_hulu():
    """将ACC成品同步到HULU"""
    data = request.get_json() or {}
    wono = data.get('wono', '')
    operator_id = data.get('operator_id', '').strip()

    # 权限校验
    permission = check_user_permission(operator_id)
    if not permission['has_permission']:
        return jsonify({
            'success': False,
            'message': '无操作权限',
            'permission_error': True,
            'reason': permission['reason'],
            'username': permission['username']
        })

    if not wono:
        return jsonify({'success': False, 'message': '请提供工单号'})

    try:
        acc_products = get_acc_products_for_sync(wono)
        if not acc_products['success']:
            return jsonify({'success': False, 'message': acc_products.get('message', 'ACC查询失败')})

        if not REDIS_AVAILABLE:
            return jsonify({'success': False, 'message': 'Redis模块未安装'})

        r = redis.Redis(host=HULU_REDIS_HOST, port=HULU_REDIS_PORT, decode_responses=True, socket_timeout=5)

        wono_prefix = wono.split('-')[0].upper() if '-' in wono else wono[:3].upper()
        prefix_to_keys = {
            'SMT': ['workorderconfig:SMT Line2', 'workorderconfig:DP SMT1'],
            'MID': ['workorderconfig:MID Line2', 'workorderconfig:DP MID1'],
            'EPP': ['workorderconfig:DP EPP1'],
            'DP': ['workorderconfig:DP EPP1', 'workorderconfig:DP MID1', 'workorderconfig:DP SMT1'],
        }
        priority_keys = prefix_to_keys.get(wono_prefix, r.keys('workorderconfig:*'))

        target_key = None
        original_data = None
        for key in priority_keys:
            try:
                if r.hexists(key, wono):
                    value = r.hget(key, wono)
                    if value:
                        original_data = json_lib.loads(value)
                        target_key = key
                        break
            except:
                continue

        if not target_key or not original_data:
            return jsonify({'success': False, 'message': f'HULU中未找到工单 {wono}'})

        acc_data = acc_products['data']
        products = acc_data.get('products', [])

        acc_finished_products = {}
        for prod in products:
            sn = prod.get('unitsn', '')
            if sn and prod.get('status') == 2:
                acc_finished_products[sn] = prod

        hulu_units = original_data.get('units', [])
        hulu_sn_set = set(u.get('unit_sn', '') for u in hulu_units)

        updated_count = 0
        inserted_count = 0

        # 收集同步记录用于日志
        sync_records = []

        for unit in hulu_units:
            unit_sn = unit.get('unit_sn', '')
            if unit_sn in acc_finished_products:
                if str(unit.get('status', '')) != '2':
                    unit['status'] = '2'
                    updated_count += 1
                    # 记录更新操作
                    sync_records.append({
                        'unitsn': unit_sn,
                        'sync_type': 'UPDATE',
                        'acc_count': 1,
                        'hulu_count': 1,
                        'result': 'SUCCESS',
                        'remark': '更新HULU状态为完成'
                    })

            ctime = unit.get('ctime', '')
            if not ctime or ctime == '':
                unit['ctime'] = '0001-01-01T00:00:00Z'
            elif 'T' not in ctime and ' ' in ctime:
                unit['ctime'] = ctime.replace(' ', 'T') + '+08:00'

        current_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
        for sn, prod in acc_finished_products.items():
            if sn not in hulu_sn_set:
                new_unit = {
                    'unit_sn': sn,
                    'status': '2',
                    'stn': prod.get('line', ''),
                    'ctime': current_time
                }
                hulu_units.append(new_unit)
                inserted_count += 1
                # 记录插入操作
                sync_records.append({
                    'unitsn': sn,
                    'sync_type': 'INSERT',
                    'acc_count': 1,
                    'hulu_count': 0,
                    'result': 'SUCCESS',
                    'remark': '新增产品到HULU'
                })

        finish_count = sum(1 for u in hulu_units if str(u.get('status', '')) == '2')
        wip_count = sum(1 for u in hulu_units if str(u.get('status', '')) != '2')
        scrap_count = int(original_data.get('scrap_count', 0))

        original_data['units'] = hulu_units
        original_data['finish_count'] = finish_count
        original_data['wip_count'] = wip_count
        original_data['last_update_time'] = current_time

        try:
            r.hset(target_key, wono, json_lib.dumps(original_data, ensure_ascii=False))
        except redis.ResponseError as e:
            error_msg = str(e)
            if 'MISCONF' in error_msg:
                return jsonify({
                    'success': False,
                    'message': 'HULU系统暂时不可用，无法同步数据，请稍后重试',
                    'error_type': 'REDIS_READONLY',
                    'user_tip': '如持续出现此问题，请联系运维检查'
                })
            raise

        # 记录操作日志 - 每条产品单独记录
        if sync_records:
            # 从original_data获取产线和型号信息
            hulu_line = original_data.get('line', target_key.replace('workorderconfig:', ''))
            hulu_partno = original_data.get('part_no', '')
            log_hulu_sync_batch(
                sync_records=sync_records,
                operator=operator_id,
                wono=wono,
                partno=hulu_partno,
                linename=hulu_line
            )

        return jsonify({
            'success': True,
            'message': f'同步成功（仅同步成品）',
            'synced': {
                'acc_finished': len(acc_finished_products),
                'updated': updated_count,
                'inserted': inserted_count,
                'total': updated_count + inserted_count,
                'hulu_finished': finish_count,
                'hulu_wip': wip_count,
                'target_key': target_key
            }
        })

    except redis.ResponseError as e:
        error_msg = str(e)
        if 'MISCONF' in error_msg:
            return jsonify({
                'success': False,
                'message': 'HULU系统暂时不可用，请稍后重试',
                'error_type': 'REDIS_READONLY',
                'user_tip': '如持续出现此问题，请联系运维检查'
            })
        print(f"Redis错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'HULU数据读取失败，请联系运维检查'})
    except Exception as e:
        print(f"同步错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': '同步操作出现异常，请稍后重试'})


@hulu_bp.route('/api/hulu_workorder')
def get_hulu_workorder():
    """获取HULU工单数据"""
    wono = request.args.get('wono', '')
    if not wono:
        return jsonify({'success': False, 'message': '请提供工单号'})

    include_details = request.args.get('include_details', 'true').lower() in ['true', '1', '']
    list_type = request.args.get('list_type', '')

    try:
        hulu_data = fetch_hulu_data(wono)

        response = {
            'success': True,
            'order_info': hulu_data.get('order_info', {}),
            'production': hulu_data.get('production', {})
        }

        if list_type == 'wip':
            response['wip_list'] = hulu_data.get('wip_list', [])
        elif list_type == 'finished':
            response['finished_list'] = hulu_data.get('finished_list', [])
        elif include_details:
            response['info_list'] = hulu_data.get('info_list', [])
            response['wip_list'] = hulu_data.get('wip_list', [])
            response['finished_list'] = hulu_data.get('finished_list', [])

        return jsonify(response)
    except Exception as e:
        print(f"HULU API错误: {e}")
        error_msg = str(e)
        if 'MISCONF' in error_msg or 'Redis' in error_msg or 'redis' in error_msg:
            return jsonify({'success': False, 'message': 'HULU系统暂时不可用，请稍后重试'})
        elif 'Connection' in error_msg or 'connect' in error_msg.lower():
            return jsonify({'success': False, 'message': 'HULU系统连接失败，请稍后重试'})
        else:
            return jsonify({'success': False, 'message': 'HULU数据读取失败，请联系运维检查'})


@hulu_bp.route('/api/hulu/diff_products')
def get_hulu_diff_products():
    """查询ACC与HULU的差异产品列表"""
    wono = request.args.get('wono', '')
    diff_type = request.args.get('diff_type', 'finished')

    if not wono:
        return jsonify({'success': False, 'message': '请提供工单号'})

    try:
        acc_products = get_acc_products_for_sync(wono)
        if not acc_products['success']:
            return jsonify({'success': False, 'message': acc_products.get('message', 'ACC查询失败')})

        products = acc_products['data'].get('products', [])

        if diff_type == 'finished':
            acc_sns = set(p['unitsn'] for p in products if p.get('status') == 2)
        else:
            acc_sns = set(p['unitsn'] for p in products if p.get('status') != 2)

        if not REDIS_AVAILABLE:
            return jsonify({'success': False, 'message': 'Redis模块未安装'})

        r = redis.Redis(host=HULU_REDIS_HOST, port=HULU_REDIS_PORT, decode_responses=True, socket_timeout=5)

        wono_prefix = wono.split('-')[0].upper() if '-' in wono else wono[:3].upper()
        prefix_to_keys = {
            'SMT': ['workorderconfig:SMT Line2', 'workorderconfig:DP SMT1'],
            'MID': ['workorderconfig:MID Line2', 'workorderconfig:DP MID1'],
            'EPP': ['workorderconfig:DP EPP1'],
            'DP': ['workorderconfig:DP EPP1', 'workorderconfig:DP MID1', 'workorderconfig:DP SMT1'],
        }
        priority_keys = prefix_to_keys.get(wono_prefix, r.keys('workorderconfig:*'))

        hulu_data = None
        for key in priority_keys:
            try:
                if r.hexists(key, wono):
                    value = r.hget(key, wono)
                    if value:
                        hulu_data = json_lib.loads(value)
                        break
            except:
                continue

        if not hulu_data:
            return jsonify({
                'success': True,
                'diff_type': diff_type,
                'diff_products': list(acc_sns),
                'acc_count': len(acc_sns),
                'hulu_count': 0,
                'diff_count': len(acc_sns)
            })

        hulu_units = hulu_data.get('units', [])
        if diff_type == 'finished':
            hulu_sns = set(u.get('unit_sn', '') for u in hulu_units if str(u.get('status', '')) == '2')
        else:
            hulu_sns = set(u.get('unit_sn', '') for u in hulu_units if str(u.get('status', '')) != '2')

        diff_sns = acc_sns - hulu_sns

        return jsonify({
            'success': True,
            'diff_type': diff_type,
            'diff_products': sorted(list(diff_sns)),
            'acc_count': len(acc_sns),
            'hulu_count': len(hulu_sns),
            'diff_count': len(diff_sns)
        })

    except redis.ResponseError as e:
        error_msg = str(e)
        if 'MISCONF' in error_msg:
            return jsonify({
                'success': False,
                'message': 'HULU系统暂时不可用，请稍后重试',
                'error_type': 'REDIS_READONLY',
                'user_tip': '如持续出现此问题，请联系运维检查'
            })
        print(f"Redis错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'HULU数据读取失败，请联系运维检查'})
    except Exception as e:
        print(f"差异查询错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': '差异查询出现异常，请稍后重试'})

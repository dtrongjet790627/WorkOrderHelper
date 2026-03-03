# -*- coding: utf-8 -*-
"""EAI日志相关路由"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from config.database import EAI_SERVER, EAI_LOG_FILES, EAI_ISSUE_LOG_FILES, EAI_ISSUE_LOG_FILE_NEW
from utils.line_identifier import identify_line
from utils.ssh_helper import ssh_execute_command
from utils.log_parser import (
    should_include_log_line, parse_eai_log_line,
    should_include_issue_log_line, parse_issue_log_line,
    should_include_erp_to_mes_log, parse_erp_to_mes_log_line, merge_erp_to_mes_logs
)

eai_logs_bp = Blueprint('eai_logs', __name__)


@eai_logs_bp.route('/api/eai_logs', methods=['POST'])
def get_eai_logs():
    """获取EAI接口日志"""
    try:
        data = request.json or {}
        wono = data.get('wono', '').strip()
        line_key = data.get('line_key', '').strip()
        limit = int(data.get('limit', 100))
        level_filter = data.get('level', '').upper()

        # 根据工单号自动识别产线
        if wono and not line_key:
            line_key = identify_line(wono)

        # 确定要查询的日志文件
        log_files_to_query = []
        if line_key and line_key in EAI_LOG_FILES:
            log_files_to_query = [(line_key, EAI_LOG_FILES[line_key])]
        else:
            log_files_to_query = list(EAI_LOG_FILES.items())

        all_logs = []

        for lk, log_file in log_files_to_query:
            remote_path = EAI_SERVER['log_path'] + log_file

            if wono:
                cmd = f"grep -i '{wono}' '{remote_path}' 2>/dev/null | tail -n {limit}"
            else:
                cmd = f"tail -n {limit} '{remote_path}' 2>/dev/null"

            try:
                success, output, error_msg = ssh_execute_command(cmd, timeout=30)

                if success and output:
                    lines = output.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            if not should_include_log_line(line):
                                continue

                            parsed = parse_eai_log_line(line)
                            if not parsed.get('raw') and not parsed.get('schb_no') and not parsed.get('error_msg'):
                                continue

                            parsed['line_key'] = lk
                            parsed['log_file'] = log_file

                            if level_filter and parsed['level'] != level_filter:
                                continue

                            all_logs.append(parsed)
                elif not success:
                    all_logs.append({
                        'level': 'ERROR',
                        'raw': f'[{lk}] {error_msg}',
                        'line_key': lk,
                        'log_file': log_file
                    })
                elif error_msg:
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

        # 处理日志
        requests = []
        triggers = []
        error_logs = []
        processed_logs = []
        error_trigger_groups = set()
        success_trigger_groups = set()
        temp_group_error_msg = {}  # 临时存储：group_id → 错误信息

        for log in all_logs:
            if log.get('log_type') == 'request':
                requests.append(log)
            elif log.get('log_type') == 'response' and log.get('status') == 'failed':
                error_logs.append(log)  # 纳入时间匹配以提取错误信息
            elif log.get('log_type') == 'trigger' and log.get('all_records'):
                triggers.append(log)

                records = log.get('all_records', [])
                base_time = log.get('time', '')
                log_line_key = log.get('line_key', '')
                log_file = log.get('log_file', '')

                if wono:
                    filtered_records = [r for r in records if r.get('WONO', '').upper() == wono.upper()]
                    if not filtered_records:
                        continue
                    records = filtered_records

                total_count = len(records)

                for idx, record in enumerate(records):
                    is_first = (idx == 0)
                    expanded_log = {
                        'time': base_time if is_first else '',
                        'level': 'INFO' if is_first else '',
                        'log_type': 'trigger',
                        'status': 'pending',  # 统一用 'pending'，失败时由后续逻辑统一更新
                        'wono': record.get('WONO'),
                        'batch': record.get('PACKID'),
                        'partno': record.get('PARTNO'),
                        'qty': record.get('CNT'),
                        'line_name': record.get('LINE'),
                        'line_key': log_line_key if is_first else '',
                        'log_file': log_file,
                        'schb_no': None,
                        'raw': f'待报工({total_count}条)' if is_first else '',
                        'is_group_first': is_first,
                        'group_id': base_time,
                        'group_order': idx
                    }
                    processed_logs.append(expanded_log)
            else:
                if log.get('log_type') == 'error' and log.get('status') == 'failed':
                    error_logs.append(log)
                else:
                    processed_logs.append(log)

        # 处理error日志
        for log in error_logs:
            log_time = log.get('time', '')
            log_wono = log.get('wono', '')
            best_trigger = None
            best_time_diff = 999999

            for trigger in triggers:
                trigger_time = trigger.get('time', '')
                if trigger_time and log_time and trigger_time <= log_time:
                    try:
                        trigger_dt = datetime.strptime(trigger_time, '%Y-%m-%d %H:%M:%S')
                        log_dt = datetime.strptime(log_time, '%Y-%m-%d %H:%M:%S')
                        time_diff = (log_dt - trigger_dt).total_seconds()
                        if time_diff <= 60 and time_diff < best_time_diff:
                            if log_wono:
                                trigger_records = trigger.get('all_records', [])
                                for rec in trigger_records:
                                    if rec.get('WONO') == log_wono:
                                        best_trigger = trigger
                                        best_time_diff = time_diff
                                        break
                            if not best_trigger or (not log_wono and time_diff < best_time_diff):
                                best_trigger = trigger
                                best_time_diff = time_diff
                    except:
                        pass

            if best_trigger:
                trigger_group_id = best_trigger.get('time', '')
                log['group_id'] = trigger_group_id
                log['group_order'] = 999
                error_trigger_groups.add(trigger_group_id)
                # 捕获错误信息供触发行显示：优先保留更详细（更长）的错误信息
                new_err = log.get('error_msg')
                if new_err:
                    existing_err = temp_group_error_msg.get(trigger_group_id, '')
                    if len(new_err) > len(existing_err):
                        temp_group_error_msg[trigger_group_id] = new_err
                # 已匹配的错误日志（response/error 类型）不需要单独显示，
                # 错误信息已合并到触发行展示
                continue

            processed_logs.append(log)

        # 合并请求和响应
        merged_logs = []
        used_requests = set()

        for log in processed_logs:
            if log.get('log_type') == 'response' and log.get('status') == 'success':
                log_time = log.get('time', '')
                log_line = log.get('line_key', '')

                best_req = None
                best_idx = -1
                for idx, req in enumerate(requests):
                    if idx in used_requests:
                        continue
                    if req.get('line_key') != log_line:
                        continue
                    req_time = req.get('time', '')
                    if req_time and log_time and req_time <= log_time:
                        if best_req is None or req_time > best_req.get('time', ''):
                            best_req = req
                            best_idx = idx

                if best_req:
                    log['wono'] = best_req.get('wono')
                    log['batch'] = best_req.get('batch')
                    log['partno'] = best_req.get('partno')
                    log['qty'] = best_req.get('qty')
                    used_requests.add(best_idx)
                else:
                    # 方法2：从请求中查找（不限制line_key，放宽条件）
                    for idx, req in enumerate(requests):
                        if idx in used_requests:
                            continue
                        req_time = req.get('time', '')
                        if req_time and log_time and req_time <= log_time:
                            try:
                                req_dt = datetime.strptime(req_time, '%Y-%m-%d %H:%M:%S')
                                log_dt = datetime.strptime(log_time, '%Y-%m-%d %H:%M:%S')
                                if (log_dt - req_dt).total_seconds() <= 10:
                                    log['wono'] = req.get('wono')
                                    log['batch'] = req.get('batch')
                                    log['partno'] = req.get('partno')
                                    log['qty'] = req.get('qty')
                                    used_requests.add(idx)
                                    break
                            except:
                                pass

                    # 方法3：从触发数据中查找工单信息（备用）
                    if not log.get('wono'):
                        for trigger in triggers:
                            trigger_time = trigger.get('time', '')
                            if trigger_time and log_time and trigger_time <= log_time:
                                try:
                                    trigger_dt = datetime.strptime(trigger_time, '%Y-%m-%d %H:%M:%S')
                                    log_dt = datetime.strptime(log_time, '%Y-%m-%d %H:%M:%S')
                                    if (log_dt - trigger_dt).total_seconds() <= 60:
                                        records = trigger.get('all_records', [])
                                        if records:
                                            first_record = records[0]
                                            log['wono'] = first_record.get('WONO')
                                            log['batch'] = first_record.get('PACKID')
                                            log['partno'] = first_record.get('PARTNO')
                                            log['qty'] = first_record.get('CNT')
                                            break
                                except:
                                    pass

                # 成功响应不关联到trigger组，单独显示
                # 这样response可以独立显示"成功"状态和汇报单号
                # trigger保持显示"待报工"状态

            merged_logs.append(log)

        all_logs = merged_logs

        # 更新trigger状态：只有失败时才更新，成功时保持"待报工"原样
        # 这样用户可以看到：trigger显示"待报工(X条)"，response显示"成功"+汇报单号

        # 构建 group_id → 错误信息的映射
        group_error_msg = dict(temp_group_error_msg)  # 从预建的映射开始
        for log in all_logs:
            if log.get('log_type') == 'error' and log.get('group_id'):
                gid = log.get('group_id')
                if gid not in group_error_msg and log.get('error_msg'):
                    group_error_msg[gid] = log.get('error_msg')

        for log in all_logs:
            if log.get('log_type') == 'trigger':
                group_id = log.get('group_id')
                if group_id in error_trigger_groups:
                    # 整组失败：更新所有子记录的状态（包括非首行）
                    log['status'] = 'failed'
                    log['level'] = 'ERROR'
                    if log.get('is_group_first'):
                        # 首行：显示错误信息
                        err_msg = group_error_msg.get(group_id)
                        if err_msg:
                            short_msg = err_msg[:60] + '...' if len(err_msg) > 60 else err_msg
                            log['raw'] = f'<span class="text-danger" title="{err_msg}">{short_msg}</span>'
                            log['error_msg'] = err_msg
                        else:
                            log['raw'] = '<span class="text-danger">报工失败</span>'
                    # 非首行：status/level 已更新为 failed/ERROR，raw 保持为空字符串（前端 rowspan 不显示详情列）
                # 成功时不更新trigger，保持原始的"待报工"状态

        # 排序
        def sort_key(x):
            group_id = x.get('group_id') or x.get('time') or ''
            group_order = x.get('group_order', 0)
            return (group_id, -group_order)

        all_logs.sort(key=sort_key, reverse=True)
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


@eai_logs_bp.route('/api/eai_logs/recent_errors', methods=['GET'])
def get_eai_recent_errors():
    """获取最近的EAI接口错误日志"""
    try:
        all_errors = []

        for lk, log_file in EAI_LOG_FILES.items():
            remote_path = EAI_SERVER['log_path'] + log_file
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
                pass

        all_errors.sort(key=lambda x: x.get('time', '') or '', reverse=True)

        return jsonify({
            'success': True,
            'errors': all_errors[:50],
            'count': len(all_errors)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@eai_logs_bp.route('/api/eai_logs/test', methods=['GET'])
def test_eai_connection():
    """测试EAI服务器SSH连接"""
    try:
        cmd = "ls -la /var/eai/logs/ | grep -i 'MES' | grep -v '.gz' | head -5"
        success, output, error_msg = ssh_execute_command(cmd, timeout=15)

        if success:
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


@eai_logs_bp.route('/api/issue_logs', methods=['POST'])
def get_issue_logs():
    """获取ERP下达工单日志（ERP→MES方向）"""
    try:
        data = request.json or {}
        wono = data.get('wono', '').strip()
        line_key = data.get('line_key', '').strip()
        action_filter = data.get('action', '').lower()  # create/update/delete
        level_filter = data.get('level', '').upper()
        limit = int(data.get('limit', 200))

        # 根据工单号自动识别产线
        if wono and not line_key:
            line_key = identify_line(wono)

        # 确定要查询的日志文件
        log_files_to_query = []
        if line_key and line_key in EAI_ISSUE_LOG_FILES:
            log_files_to_query = [(line_key, EAI_ISSUE_LOG_FILES[line_key])]
        else:
            log_files_to_query = list(EAI_ISSUE_LOG_FILES.items())

        all_logs = []

        for lk, log_file in log_files_to_query:
            remote_path = EAI_SERVER['log_path'] + log_file

            if wono:
                cmd = f"grep -i '{wono}' '{remote_path}' 2>/dev/null | tail -n {limit}"
            else:
                cmd = f"tail -n {limit * 2} '{remote_path}' 2>/dev/null"

            try:
                success, output, error_msg = ssh_execute_command(cmd, timeout=30)

                if success and output:
                    lines = output.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            if not should_include_issue_log_line(line):
                                continue

                            parsed = parse_issue_log_line(line)
                            if not parsed.get('raw') and not parsed.get('wono'):
                                continue

                            parsed['line_key'] = lk
                            parsed['log_file'] = log_file

                            # 应用筛选条件
                            if level_filter:
                                if level_filter == 'SUCCESS' and parsed['level'] != 'SUCCESS':
                                    continue
                                if level_filter == 'ERROR' and parsed['level'] != 'ERROR':
                                    continue

                            if action_filter and parsed.get('action') != action_filter:
                                continue

                            all_logs.append(parsed)

                elif not success:
                    all_logs.append({
                        'level': 'ERROR',
                        'raw': f'[{lk}] {error_msg}',
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

        # 合并请求和响应日志
        merged_logs = []
        requests = [log for log in all_logs if log.get('log_type') == 'request']
        responses = [log for log in all_logs if log.get('log_type') in ('response', 'success', 'error')]
        other_logs = [log for log in all_logs if log.get('log_type') not in ('request', 'response', 'success', 'error')]

        used_requests = set()

        for resp in responses:
            resp_time = resp.get('time', '')
            resp_wono = resp.get('wono', '')

            # 找匹配的请求
            best_req = None
            best_idx = -1
            for idx, req in enumerate(requests):
                if idx in used_requests:
                    continue
                req_time = req.get('time', '')
                req_wono = req.get('wono', '')

                # 工单号匹配
                if req_wono and resp_wono and req_wono == resp_wono:
                    if best_req is None or req_time > best_req.get('time', ''):
                        best_req = req
                        best_idx = idx
                # 时间匹配（10秒内）
                elif req_time and resp_time and req_time <= resp_time:
                    try:
                        req_dt = datetime.strptime(req_time, '%Y-%m-%d %H:%M:%S')
                        resp_dt = datetime.strptime(resp_time, '%Y-%m-%d %H:%M:%S')
                        if (resp_dt - req_dt).total_seconds() <= 10:
                            if best_req is None:
                                best_req = req
                                best_idx = idx
                    except:
                        pass

            if best_req:
                # 合并请求信息到响应
                resp['wono'] = resp.get('wono') or best_req.get('wono')
                resp['partno'] = resp.get('partno') or best_req.get('partno')
                resp['plan_qty'] = resp.get('plan_qty') or best_req.get('plan_qty')
                resp['action'] = resp.get('action') or best_req.get('action')
                used_requests.add(best_idx)

            merged_logs.append(resp)

        # 添加未匹配的请求（可能还在处理中）
        for idx, req in enumerate(requests):
            if idx not in used_requests:
                req['status'] = 'pending'
                merged_logs.append(req)

        # 添加其他日志
        merged_logs.extend(other_logs)

        # 按时间倒序排序
        merged_logs.sort(key=lambda x: x.get('time') or '', reverse=True)
        merged_logs = merged_logs[:limit]

        # 统计
        summary = {
            'total': len(merged_logs),
            'success': sum(1 for log in merged_logs if log.get('status') == 'success'),
            'failed': sum(1 for log in merged_logs if log.get('status') == 'failed'),
            'pending': sum(1 for log in merged_logs if log.get('status') == 'pending'),
            'create': sum(1 for log in merged_logs if log.get('action') == 'create'),
            'update': sum(1 for log in merged_logs if log.get('action') == 'update'),
            'delete': sum(1 for log in merged_logs if log.get('action') == 'delete')
        }

        return jsonify({
            'success': True,
            'logs': merged_logs,
            'summary': summary,
            'query_info': {
                'wono': wono or '全部',
                'line_key': line_key or '全部产线',
                'action_filter': action_filter or '全部',
                'level_filter': level_filter or '全部',
                'limit': limit
            }
        })

    except Exception as e:
        return jsonify({'error': f'查询下达工单日志失败: {str(e)}'}), 500


@eai_logs_bp.route('/api/erp_to_mes_logs', methods=['POST'])
def get_erp_to_mes_logs():
    """获取ERP发送到MES接口日志（新版下达工单日志）

    日志文件位置: /var/eai/logs/FLOW_ERP发送到MES接口.log
    """
    try:
        data = request.json or {}
        wono = data.get('wono', '').strip()
        proline_filter = data.get('proline', '').strip()  # 产线筛选
        level_filter = data.get('level', '').upper()
        limit = int(data.get('limit', 300))

        log_file = EAI_ISSUE_LOG_FILE_NEW
        remote_path = EAI_SERVER['log_path'] + log_file

        # 构建查询命令
        if wono:
            # 按工单号搜索
            cmd = f"grep -i '{wono}' '{remote_path}' 2>/dev/null | tail -n {limit * 2}"
        else:
            # 获取最新日志
            cmd = f"tail -n {limit * 3} '{remote_path}' 2>/dev/null"

        all_logs = []

        try:
            success, output, error_msg = ssh_execute_command(cmd, timeout=30)

            if success and output:
                lines = output.strip().split('\n')
                # 记录上一个error_detail行的索引，用于合并>>>行的错误详情
                last_error_detail_idx = -1

                for line in lines:
                    if line.strip():
                        # 过滤无用日志
                        if not should_include_erp_to_mes_log(line):
                            continue

                        # 解析日志
                        parsed = parse_erp_to_mes_log_line(line)

                        # 处理跨行错误详情（>>>开头的行）
                        # 这类行没有时间戳，需要合并到前面的error_detail行
                        if parsed.get('log_type') == 'error_detail_multiline':
                            # 找最近的error_detail行（没有error_msg的）
                            if last_error_detail_idx >= 0 and last_error_detail_idx < len(all_logs):
                                prev_log = all_logs[last_error_detail_idx]
                                if prev_log.get('log_type') == 'error_detail' and not prev_log.get('error_msg'):
                                    # 将错误信息合并到前一行
                                    prev_log['error_msg'] = parsed.get('error_msg')
                                    prev_log['raw'] = f'<span class="text-danger">{parsed.get("error_msg", "")}</span>'
                                    # 不将>>>行单独添加到日志中
                                    continue

                        # error_detail行即使没有raw也要保留，等待与>>>行合并
                        if parsed.get('log_type') == 'error_detail':
                            # 先添加，后面会与>>>行合并
                            pass
                        elif not parsed.get('raw') and not parsed.get('wono'):
                            continue

                        parsed['log_file'] = log_file

                        # 记录error_detail行的位置
                        if parsed.get('log_type') == 'error_detail':
                            last_error_detail_idx = len(all_logs)

                        all_logs.append(parsed)

            elif not success:
                all_logs.append({
                    'level': 'ERROR',
                    'raw': f'日志读取失败: {error_msg}',
                    'log_file': log_file
                })

        except Exception as e:
            all_logs.append({
                'level': 'ERROR',
                'raw': f'读取异常: {str(e)[:100]}',
                'log_file': log_file
            })

        # 合并请求和响应
        merged_logs = merge_erp_to_mes_logs(all_logs)

        # 应用筛选条件
        filtered_logs = []
        for log in merged_logs:
            # 产线筛选
            if proline_filter:
                log_proline = (log.get('proline') or '').lower()
                if proline_filter.lower() not in log_proline:
                    continue

            # 状态筛选
            if level_filter:
                if level_filter == 'SUCCESS' and log.get('status') != 'success':
                    continue
                if level_filter == 'ERROR' and log.get('status') != 'failed':
                    continue

            filtered_logs.append(log)

        # 限制返回数量
        filtered_logs = filtered_logs[:limit]

        # 统计
        summary = {
            'total': len(filtered_logs),
            'success': sum(1 for log in filtered_logs if log.get('status') == 'success'),
            'failed': sum(1 for log in filtered_logs if log.get('status') == 'failed'),
            'pending': sum(1 for log in filtered_logs if log.get('status') == 'pending')
        }

        return jsonify({
            'success': True,
            'logs': filtered_logs,
            'summary': summary,
            'query_info': {
                'wono': wono or '全部',
                'proline': proline_filter or '全部产线',
                'level_filter': level_filter or '全部',
                'limit': limit
            }
        })

    except Exception as e:
        return jsonify({'error': f'查询ERP发送到MES日志失败: {str(e)}'}), 500

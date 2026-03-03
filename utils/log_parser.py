# -*- coding: utf-8 -*-
"""EAI日志解析函数"""

import re
import json as json_module
from datetime import datetime


def should_include_log_line(line):
    """判断日志行是否应该包含在结果中

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

    Args:
        line: 日志行

    Returns:
        bool: 是否应该包含
    """
    line_lower = line.lower()

    # ===== 必须保留的关键信息 =====
    # 触发器获取到数据
    if 'db trigger get data' in line_lower:
        return True

    # ERP响应 - 保留所有响应（成功和失败）
    if 'kingdee response' in line_lower:
        return True  # 保留所有响应（成功和失败）

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
    """解析EAI日志行，提取关键信息

    只处理有用的日志类型：
    1. 触发器数据（db trigger get data）- 展示所有待处理记录
    2. ERP响应（kingdee response）- 提取成功/失败状态和错误信息
    3. 执行错误（run error）- 提取详细错误信息
    4. 流程状态（run failed/success）

    Args:
        line: 日志行

    Returns:
        dict: 解析后的日志信息
    """
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
        'all_records': None
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
        result['status'] = 'pending'
        json_match = re.search(r'db trigger get data:\s*(\[.*)', line)
        if json_match:
            json_str = json_match.group(1)
            try:
                try:
                    records = json_module.loads(json_str)
                except json_module.JSONDecodeError:
                    last_brace = json_str.rfind('}')
                    if last_brace > 0:
                        fixed_json = json_str[:last_brace+1] + ']'
                        records = json_module.loads(fixed_json)
                    else:
                        records = []

                if records and isinstance(records, list):
                    result['record_count'] = len(records)
                    result['all_records'] = records
                    first_record = records[0]
                    result['wono'] = first_record.get('WONO')
                    result['batch'] = first_record.get('PACKID')
                    result['qty'] = first_record.get('CNT')
                    result['partno'] = first_record.get('PARTNO')
                    result['line_name'] = first_record.get('LINE')

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
        wono_match = re.search(r'\\?"FMoBillNo\\?"\s*:\s*\\?"([^"\\]+)\\?"', line)
        if wono_match:
            result['wono'] = wono_match.group(1)
        batch_match = re.search(r'\\?"FLot\\?"\s*:\s*\{?\s*\\?"FNumber\\?"\s*:\s*\\?"([^"\\]+)\\?"', line)
        if batch_match:
            result['batch'] = batch_match.group(1)
        partno_match = re.search(r'\\?"FMaterialId\\?"\s*:\s*\{?\s*\\?"FNumber\\?"\s*:\s*\\?"([^"\\]+)\\?"', line)
        if partno_match:
            result['partno'] = partno_match.group(1)
        qty_match = re.search(r'\\?"FFinishQty\\?"\s*:\s*(\d+)', line)
        if qty_match:
            result['qty'] = qty_match.group(1)
        result['raw'] = '发送报工请求'
        return result

    # ========== 3. 处理ERP响应 ==========
    if 'kingdee response' in line.lower():
        result['log_type'] = 'response'
        schb_match = re.search(r'"Number"\s*:\s*"(SCHB\d+)"', line)
        if schb_match:
            result['schb_no'] = schb_match.group(1)

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
                result['raw'] = None
        return result

    # ========== 4. 处理执行错误（run error） ==========
    if 'run error' in line.lower():
        result['log_type'] = 'error'
        result['status'] = 'failed'
        result['level'] = 'ERROR'

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

        # 方法1：提取 JSON 中的 Message 字段（可能有或没有反斜杠转义）
        msg_match = re.search(r'\\?"Message\\?"\s*:\s*\\?"([^"\\]+)\\?"', line)
        if msg_match:
            result['error_msg'] = msg_match.group(1)

        # 方法2：如果方法1没提取到，尝试提取 "run error:" 后面的详细内容
        # 格式示例：... run error: 生产汇报单【SCHB00079142】的明细第1行 ...
        if not result['error_msg']:
            run_error_match = re.search(r'run\s+error[：:]\s*(.+)', line, re.IGNORECASE)
            if run_error_match:
                candidate = run_error_match.group(1).strip()
                # 排除仅包含 JSON 嵌套结构头部（call lua error 等）的情况
                # 有意义的错误信息通常包含中文或业务关键词
                if candidate and len(candidate) > 5:
                    result['error_msg'] = candidate

        if result['error_msg']:
            result['raw'] = f'<span class="text-danger">{result["error_msg"]}</span>'
        else:
            result['raw'] = '<span class="text-danger">执行错误</span>'
        return result

    # ========== 5. 处理流程执行状态 ==========
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

    # ========== 6. 兜底：其他错误日志 ==========
    if result['level'] == 'ERROR':
        result['log_type'] = 'error'
        result['status'] = 'failed'
        wono_match = re.search(r'"(?:WONO|FMoBillNo)"\s*:\s*"([^"]+)"', line)
        if wono_match:
            result['wono'] = wono_match.group(1)
        batch_match = re.search(r'"(?:PACKID|FNumber)"\s*:\s*"([^"]+)"', line)
        if batch_match:
            result['batch'] = batch_match.group(1)
        simplified = re.sub(r'^\[.*?\]\[.*?\]\[.*?\]\[.*?\]\s*>+\s*', '', line.strip())
        result['raw'] = f'<span class="text-danger">{simplified}</span>'

    return result


def should_include_issue_log_line(line):
    """判断下达工单日志行是否应该包含在结果中

    保留有用信息：
    1. 接收到工单数据（收到请求）
    2. 处理结果（成功/失败）
    3. 错误日志

    Args:
        line: 日志行

    Returns:
        bool: 是否应该包含
    """
    line_lower = line.lower()

    # 接收到数据
    if 'request' in line_lower or '请求' in line_lower:
        return True

    # 响应/结果
    if 'response' in line_lower or 'result' in line_lower:
        return True

    # 成功/失败状态
    if 'success' in line_lower or 'failed' in line_lower or 'error' in line_lower:
        return True

    # 工单相关关键词
    if 'workorder' in line_lower or 'wono' in line_lower or '工单' in line_lower:
        return True

    # 错误日志
    if '[erro]' in line_lower or '[error]' in line_lower:
        return True

    return False


def parse_issue_log_line(line):
    """解析下达工单日志行，提取关键信息

    Args:
        line: 日志行

    Returns:
        dict: 解析后的日志信息
    """
    result = {
        'time': None,
        'level': 'INFO',
        'wono': None,
        'partno': None,
        'plan_qty': None,
        'action': None,  # create/update/delete
        'status': None,
        'error_msg': None,
        'raw': None,
        'log_type': None
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

    # ========== 1. 处理请求数据 ==========
    if 'request' in line.lower() or '请求' in line:
        result['log_type'] = 'request'

        # 提取工单号 - 多种格式匹配
        wono_patterns = [
            r'"FBillNo"\s*:\s*"([^"]+)"',
            r'"WONO"\s*:\s*"([^"]+)"',
            r'\\?"FBillNo\\?"\s*:\s*\\?"([^"\\]+)\\?"',
            r'工单[号]?\s*[：:]\s*(\S+)',
        ]
        for pattern in wono_patterns:
            wono_match = re.search(pattern, line, re.IGNORECASE)
            if wono_match:
                result['wono'] = wono_match.group(1)
                break

        # 提取型号
        partno_patterns = [
            r'"FMaterialId"\s*:\s*\{?\s*"FNumber"\s*:\s*"([^"]+)"',
            r'"PARTNO"\s*:\s*"([^"]+)"',
            r'\\?"FMaterialId\\?"\s*:\s*\{?\s*\\?"FNumber\\?"\s*:\s*\\?"([^"\\]+)\\?"',
        ]
        for pattern in partno_patterns:
            partno_match = re.search(pattern, line, re.IGNORECASE)
            if partno_match:
                result['partno'] = partno_match.group(1)
                break

        # 提取计划数量
        qty_patterns = [
            r'"FQty"\s*:\s*(\d+)',
            r'"PLANQTY"\s*:\s*(\d+)',
            r'\\?"FQty\\?"\s*:\s*(\d+)',
        ]
        for pattern in qty_patterns:
            qty_match = re.search(pattern, line, re.IGNORECASE)
            if qty_match:
                result['plan_qty'] = qty_match.group(1)
                break

        # 判断操作类型
        if 'save' in line.lower() or 'create' in line.lower() or '新增' in line:
            result['action'] = 'create'
            result['raw'] = '接收工单(新增)'
        elif 'update' in line.lower() or '修改' in line:
            result['action'] = 'update'
            result['raw'] = '接收工单(修改)'
        elif 'delete' in line.lower() or '删除' in line:
            result['action'] = 'delete'
            result['raw'] = '接收工单(删除)'
        else:
            result['raw'] = '接收工单'

        return result

    # ========== 2. 处理响应/结果 ==========
    if 'response' in line.lower() or 'result' in line.lower():
        result['log_type'] = 'response'

        # 提取工单号
        wono_match = re.search(r'"(?:FBillNo|WONO|Number)"\s*:\s*"([^"]+)"', line, re.IGNORECASE)
        if wono_match:
            result['wono'] = wono_match.group(1)

        if '"IsSuccess":true' in line or '"IsSuccess": true' in line or 'success' in line.lower():
            result['status'] = 'success'
            result['level'] = 'SUCCESS'
            result['raw'] = '<span class="text-success">处理成功</span>'
        elif '"IsSuccess":false' in line or '"IsSuccess": false' in line or 'fail' in line.lower():
            result['status'] = 'failed'
            result['level'] = 'ERROR'
            msg_match = re.search(r'"Message"\s*:\s*"([^"]+)"', line)
            if msg_match:
                result['error_msg'] = msg_match.group(1)
                result['raw'] = f'<span class="text-danger">{result["error_msg"]}</span>'
            else:
                result['raw'] = '<span class="text-danger">处理失败</span>'

        return result

    # ========== 3. 处理错误日志 ==========
    if result['level'] == 'ERROR' or 'error' in line.lower():
        result['log_type'] = 'error'
        result['status'] = 'failed'
        result['level'] = 'ERROR'

        # 尝试提取工单号
        wono_match = re.search(r'"(?:FBillNo|WONO)"\s*:\s*"([^"]+)"', line, re.IGNORECASE)
        if wono_match:
            result['wono'] = wono_match.group(1)

        # 提取错误信息
        msg_match = re.search(r'"Message"\s*:\s*"([^"]+)"', line)
        if msg_match:
            result['error_msg'] = msg_match.group(1)
            result['raw'] = f'<span class="text-danger">{result["error_msg"]}</span>'
        else:
            simplified = re.sub(r'^\[.*?\]\[.*?\]\[.*?\]\[.*?\]\s*>+\s*', '', line.strip())
            result['raw'] = f'<span class="text-danger">{simplified}</span>'

        return result

    # ========== 4. 处理成功日志 ==========
    if 'success' in line.lower():
        result['log_type'] = 'success'
        result['status'] = 'success'
        result['level'] = 'SUCCESS'

        wono_match = re.search(r'"(?:FBillNo|WONO)"\s*:\s*"([^"]+)"', line, re.IGNORECASE)
        if wono_match:
            result['wono'] = wono_match.group(1)

        result['raw'] = '<span class="text-success">处理成功</span>'
        return result

    return result


def deduplicate_error_logs(logs):
    """去重连续相同的失败日志

    相同工单+相同批次+相同错误信息的连续失败只保留第一条

    Args:
        logs: 日志列表

    Returns:
        list: 去重后的日志列表
    """
    if not logs:
        return logs

    result = []
    seen_errors = {}

    for log in logs:
        if log.get('status') == 'success' or log.get('level') == 'SUCCESS':
            key_prefix = (log.get('wono'), log.get('batch'))
            keys_to_remove = [k for k in seen_errors if k[:2] == key_prefix]
            for k in keys_to_remove:
                del seen_errors[k]
            result.append(log)
        elif log.get('status') == 'failed' or log.get('level') == 'ERROR':
            key = (log.get('wono'), log.get('batch'), log.get('error_msg') or log.get('raw'))
            if key not in seen_errors:
                seen_errors[key] = log.get('time')
                result.append(log)
        else:
            result.append(log)

    return result


# ============================================
#  ERP发送到MES接口日志解析（新版下达工单日志）
# ============================================

def should_include_erp_to_mes_log(line):
    """判断ERP发送到MES日志行是否应该包含

    错误日志模式（每次失败产生多条，我们只需要关键行）：
    1. [ERRO]...xxx run error: call lua error:<string>:25:                  <- 保留（错误标记）
    2. >>>ERP的BOM中IDNAME...版本不一致                                      <- 保留（真正错误原因，跨行）
    3. [ERRO]...trigger error:...                                           <- 跳过（重复）
    4. [ERRO]...rest api server trigger error:...                           <- 跳过（重复）
    5. [ERRO]...>>>>> flow [...] run failed, cost xxx ms                    <- 保留（最终状态）

    只保留关键日志：
    1. request body - 请求数据（包含工单信息）
    2. run success - 成功状态
    3. run failed - 失败状态（最终失败记录）
    4. xxx run error: - 错误标记行
    5. >>>开头的行 - 跨行的错误详情（如">>>ERP的BOM中IDNAME..."）
    """
    line_lower = line.lower()

    # 请求数据
    if 'request body:' in line_lower:
        return True

    # 执行结果（最终状态）
    if 'run success' in line_lower:
        return True
    if 'run failed' in line_lower:
        return True

    # 跨行的错误详情（以>>>开头，包含真正的错误原因）
    if line.strip().startswith('>>>'):
        return True

    # 错误日志处理
    if '[erro]' in line_lower:
        # 跳过重复的错误日志（第2、3条）
        if 'trigger error' in line_lower:
            return False
        if 'rest api server' in line_lower:
            return False
        # 保留第一条错误日志（包含 "run error:"）
        if 'run error' in line_lower:
            return True

    return False


def parse_erp_to_mes_log_line(line):
    """解析ERP发送到MES日志行

    提取字段：
    - 时间
    - 级别 (SUCCESS/ERROR/INFO)
    - 工单号 (FBillNo)
    - 产线 (FProline) - 从FEntry数组中提取
    - 物料ID (FMaterialId)
    - 物料名称 (FMaterialName)
    - 数量 (FQty)
    - 执行耗时 (cost xxx ms)
    - 错误信息（如果有）

    Args:
        line: 日志行

    Returns:
        dict: 解析后的日志信息
    """
    result = {
        'time': None,
        'level': 'INFO',
        'wono': None,            # 工单号 FBillNo
        'bill_type': None,       # 工单类型 FBillType
        'proline': None,         # 产线 FProline
        'material_id': None,     # 物料ID FMaterialId
        'material_name': None,   # 物料名称 FMaterialName
        'qty': None,             # 数量 FQty
        'cost_ms': None,         # 执行耗时
        'status': None,          # success/failed/pending
        'error_msg': None,
        'raw': None,
        'log_type': None         # request/success/error
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

    # 提取时间戳（格式：2026-01-19 15:40:41）
    time_match = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
    if time_match:
        result['time'] = time_match.group(1)

    # ========== 1. 处理请求数据 (request body) ==========
    if 'request body:' in line.lower():
        result['log_type'] = 'request'
        result['status'] = 'pending'

        # 由于日志行通常被截断，使用正则表达式直接提取关键字段
        # 提取工单号 FBillNo
        wono_match = re.search(r'"FBillNo"\s*:\s*"([^"]+)"', line)
        if wono_match:
            result['wono'] = wono_match.group(1)

        # 提取工单类型 FBillType
        bill_type_match = re.search(r'"FBillType"\s*:\s*"([^"]+)"', line)
        if bill_type_match:
            result['bill_type'] = bill_type_match.group(1)

        # 提取产线 FProline（在FEntry数组内）
        proline_match = re.search(r'"FProline"\s*:\s*"([^"]+)"', line)
        if proline_match:
            result['proline'] = proline_match.group(1)

        # 提取物料ID FMaterialId（在FEntry数组内）
        material_id_match = re.search(r'"FMaterialId"\s*:\s*"([^"]+)"', line)
        if material_id_match:
            result['material_id'] = material_id_match.group(1)

        # 提取物料名称 FMaterialName
        material_name_match = re.search(r'"FMaterialName"\s*:\s*"([^"]+)"', line)
        if material_name_match:
            result['material_name'] = material_name_match.group(1)

        # 提取数量 FQty（匹配FEntry中的第一个FQty，通常格式为 "FQty":"9000.0000000000"）
        qty_match = re.search(r'"FQty"\s*:\s*"([\d.]+)"', line)
        if qty_match:
            try:
                qty_float = float(qty_match.group(1))
                result['qty'] = str(int(qty_float))
            except ValueError:
                result['qty'] = qty_match.group(1)

        result['raw'] = f'下达工单请求'

        return result

    # ========== 2. 处理执行成功 (run success) ==========
    if 'run success' in line.lower():
        result['log_type'] = 'success'
        result['status'] = 'success'
        result['level'] = 'SUCCESS'

        # 提取耗时
        cost_match = re.search(r'cost\s+(\d+)\s*ms', line)
        if cost_match:
            result['cost_ms'] = cost_match.group(1)
            result['raw'] = f'<span class="text-success"><b>下达成功</b></span> (耗时{result["cost_ms"]}ms)'
        else:
            result['raw'] = '<span class="text-success"><b>下达成功</b></span>'

        return result

    # ========== 3. 处理执行失败 (run failed) ==========
    if 'run failed' in line.lower():
        result['log_type'] = 'error'
        result['status'] = 'failed'
        result['level'] = 'ERROR'

        # 提取耗时
        cost_match = re.search(r'cost\s+(\d+)\s*ms', line)
        if cost_match:
            result['cost_ms'] = cost_match.group(1)
            result['raw'] = f'<span class="text-danger"><b>下达失败</b></span> (耗时{result["cost_ms"]}ms)'
        else:
            result['raw'] = '<span class="text-danger"><b>下达失败</b></span>'

        # 尝试从日志中提取错误信息
        error_match = re.search(r'error[:\s]+(.+)', line, re.IGNORECASE)
        if error_match:
            result['error_msg'] = error_match.group(1)

        return result

    # ========== 4. 处理跨行的错误详情（以>>>开头）==========
    if line.strip().startswith('>>>'):
        result['log_type'] = 'error_detail_multiline'  # 跨行的错误详情
        result['status'] = 'failed'
        result['level'] = 'ERROR'

        # 提取>>>后面的错误信息
        error_msg = line.strip()[3:].strip()  # 去掉>>>前缀
        result['error_msg'] = error_msg
        result['raw'] = f'<span class="text-danger">{error_msg}</span>'

        return result

    # ========== 5. 处理其他错误日志（提取具体错误原因）==========
    if result['level'] == 'ERROR':
        result['log_type'] = 'error_detail'  # 标记为错误详情，用于合并时提取错误原因
        result['status'] = 'failed'

        # 提取真正的错误原因
        # 格式如: "Oracle数据库查询 run error: call lua error:<string>:19: 该型号不存在"
        error_reason = None

        # 方法1：匹配 <string>:数字: 后面的内容（最常见格式）
        # 例如: call lua error:<string>:19: 该型号不存在
        lua_error_match = re.search(r'<string>:\d+:\s*(.+?)(?:\s*$|\s*stack)', line)
        if lua_error_match:
            error_reason = lua_error_match.group(1).strip()
            # 如果提取的内容为空或只有符号，说明错误信息在下一行
            if not error_reason or len(error_reason) < 2:
                error_reason = None

        # 方法2：如果方法1没找到，尝试匹配最后一个冒号后的内容
        if not error_reason:
            # 从 "run error: call lua error:..." 中提取
            last_colon_match = re.search(r':\s*([^:\[\]]{2,50})(?:\s*$|\s*stack)', line)
            if last_colon_match:
                candidate = last_colon_match.group(1).strip()
                # 排除一些无意义的匹配
                if candidate and not candidate.startswith('call') and not candidate.startswith('<'):
                    error_reason = candidate

        if error_reason:
            result['error_msg'] = error_reason
            result['raw'] = f'<span class="text-danger">{error_reason}</span>'
        else:
            # 错误信息可能在下一行（以>>>开头），此处标记为空，等待合并
            result['error_msg'] = None
            result['raw'] = None

        return result

    return result


def merge_erp_to_mes_logs(logs):
    """合并ERP到MES的请求和响应日志

    将请求日志（包含工单详细信息）和对应的成功/失败响应合并，
    使得前端可以在一行中显示完整信息。

    同时将错误详情合并到失败记录中，避免显示多行错误。

    Args:
        logs: 解析后的日志列表

    Returns:
        list: 合并后的日志列表
    """
    if not logs:
        return logs

    # 分离不同类型的日志
    requests = [log for log in logs if log.get('log_type') == 'request']
    final_responses = [log for log in logs if log.get('log_type') in ('success', 'error')]  # run success/failed
    error_details = [log for log in logs if log.get('log_type') == 'error_detail']  # 错误详情（同行）
    error_details_multiline = [log for log in logs if log.get('log_type') == 'error_detail_multiline']  # 跨行错误详情

    merged = []
    used_requests = set()
    used_error_details = set()

    for resp in final_responses:
        resp_time = resp.get('time', '')

        # 1. 找最近的请求（获取工单信息）
        best_req = None
        best_req_idx = -1
        best_time_diff = 999999

        for idx, req in enumerate(requests):
            if idx in used_requests:
                continue
            req_time = req.get('time', '')
            if req_time and resp_time and req_time <= resp_time:
                try:
                    req_dt = datetime.strptime(req_time, '%Y-%m-%d %H:%M:%S')
                    resp_dt = datetime.strptime(resp_time, '%Y-%m-%d %H:%M:%S')
                    time_diff = (resp_dt - req_dt).total_seconds()
                    # 60秒内的请求可以匹配
                    if 0 <= time_diff <= 60 and time_diff < best_time_diff:
                        best_req = req
                        best_req_idx = idx
                        best_time_diff = time_diff
                except Exception:
                    pass

        if best_req:
            # 将请求信息合并到响应中
            resp['wono'] = best_req.get('wono')
            resp['bill_type'] = best_req.get('bill_type')
            resp['proline'] = best_req.get('proline')
            resp['material_id'] = best_req.get('material_id')
            resp['material_name'] = best_req.get('material_name')
            resp['qty'] = best_req.get('qty')
            used_requests.add(best_req_idx)

        # 2. 如果是失败记录，找对应的错误详情（获取真正的错误原因）
        if resp.get('status') == 'failed' and resp.get('log_type') == 'error':
            error_reason = None

            # 首先检查同行的错误详情
            for idx, err in enumerate(error_details):
                if idx in used_error_details:
                    continue
                err_time = err.get('time', '')
                if err_time and resp_time:
                    try:
                        err_dt = datetime.strptime(err_time, '%Y-%m-%d %H:%M:%S')
                        resp_dt = datetime.strptime(resp_time, '%Y-%m-%d %H:%M:%S')
                        time_diff = abs((resp_dt - err_dt).total_seconds())
                        # 同一秒内的错误详情
                        if time_diff <= 1 and err.get('error_msg'):
                            error_reason = err.get('error_msg')
                            used_error_details.add(idx)
                            break
                    except Exception:
                        pass

            # 如果同行没找到，检查跨行的错误详情（以>>>开头的）
            if not error_reason:
                for err in error_details_multiline:
                    err_time = err.get('time', '')
                    if err_time and resp_time:
                        try:
                            err_dt = datetime.strptime(err_time, '%Y-%m-%d %H:%M:%S')
                            resp_dt = datetime.strptime(resp_time, '%Y-%m-%d %H:%M:%S')
                            time_diff = abs((resp_dt - err_dt).total_seconds())
                            # 同一秒内的错误详情
                            if time_diff <= 1 and err.get('error_msg'):
                                error_reason = err.get('error_msg')
                                break
                        except Exception:
                            pass

            if error_reason:
                # 将错误原因合并到失败记录中
                cost_ms = resp.get('cost_ms', '')
                if cost_ms:
                    resp['raw'] = f'<span class="text-danger"><b>下达失败</b>: {error_reason}</span> (耗时{cost_ms}ms)'
                else:
                    resp['raw'] = f'<span class="text-danger"><b>下达失败</b>: {error_reason}</span>'
                resp['error_msg'] = error_reason

        merged.append(resp)

    # 添加未匹配的请求（可能还在处理中）
    for idx, req in enumerate(requests):
        if idx not in used_requests:
            req['status'] = 'pending'
            merged.append(req)

    # 按时间倒序排序
    merged.sort(key=lambda x: x.get('time') or '', reverse=True)

    return merged

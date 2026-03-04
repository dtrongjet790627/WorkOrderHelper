# -*- coding: utf-8 -*-
"""部署节点相关工具"""
import os
from flask import jsonify

# 各部署节点的产线白名单（key不在此dict中 = 全部产线）
DEPLOYMENT_LINES = {
    '165': ['dpepp1', 'dpeps1', 'ceps1'],  # 全产线排除电控二线
    '168': ['smt2'],                         # 仅电控二线
}


def get_deployment():
    return os.getenv('WO_DEPLOYMENT', '')


def check_line_access(line_key):
    """检查当前部署节点是否允许访问该产线

    Returns: (allowed: bool, error_response: tuple or None)
    """
    deployment = get_deployment()
    allowed = DEPLOYMENT_LINES.get(deployment)
    if allowed is not None and line_key not in allowed:
        return False, (jsonify({'error': '此工单不属于本系统负责的产线，请在对应系统中查询'}), 403)
    return True, None

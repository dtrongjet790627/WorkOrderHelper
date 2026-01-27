# -*- coding: utf-8 -*-
"""产线识别函数"""


def identify_line(wono):
    """根据工单号识别产线

    Args:
        wono: 工单号

    Returns:
        str: 产线标识 (dpepp1/smt2/dpeps1)

    工单号格式示例：
    - SMT-226011401: 电控二线（SMT-2开头）
    - MID-226011401: 电控二线（MID-2开头）
    - SMT26011401: 电控一线（SMT开头，无-2）
    - EPS26011401: 总成DP产线
    """
    wono_upper = wono.upper()
    # 电控二线 - 以SMT-2或MID-2开头
    if wono_upper.startswith('SMT-2') or wono_upper.startswith('MID-2'):
        return 'smt2'
    # 总成DP产线
    if wono_upper.startswith('EPS') or wono_upper.startswith('IPA'):
        return 'dpeps1'
    # 电控一线
    if wono_upper.startswith(('SMT', 'MID', 'EPP')):
        return 'dpepp1'
    # 默认
    return 'dpepp1'


def identify_erp_line(wono):
    """根据工单号识别ERP数据库（电控二线用198，其他用183）

    Args:
        wono: 工单号

    Returns:
        str: ERP产线标识 (line1/line2)
    """
    wono_upper = wono.upper()
    # 电控二线：工单号含'-2'且第5-6位是'22'
    if '-2' in wono_upper:
        return 'line2'
    # 其他产线（电控一线、总成线）
    return 'line1'

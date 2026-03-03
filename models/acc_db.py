# -*- coding: utf-8 -*-
"""ACC Oracle数据库连接"""

import oracledb as cx_Oracle
from config.database import DB_CONFIG, LINE_CONFIG, IPLANT_WEB_CONFIG


def get_connection(line_key):
    """获取ACC数据库连接(Oracle)

    Args:
        line_key: 产线标识 (dpepp1/smt2/dpeps1/ceps1)

    Returns:
        cx_Oracle.Connection: 数据库连接对象
    """
    config = LINE_CONFIG[line_key]
    dsn = cx_Oracle.makedsn(DB_CONFIG['host'], DB_CONFIG['port'], service_name=DB_CONFIG['service_name'])
    return cx_Oracle.connect(user=config['user'], password=config['password'], dsn=dsn)


def get_iplant_web_connection():
    """获取iplant_web数据库连接(Oracle)

    用于查询IP_WO_WORKORDER表获取工单计划数量

    Returns:
        cx_Oracle.Connection: 数据库连接对象
    """
    dsn = cx_Oracle.makedsn(DB_CONFIG['host'], DB_CONFIG['port'], service_name=DB_CONFIG['service_name'])
    return cx_Oracle.connect(user=IPLANT_WEB_CONFIG['user'], password=IPLANT_WEB_CONFIG['password'], dsn=dsn)

# -*- coding: utf-8 -*-
"""ERP SQL Server数据库连接"""

import pymssql
from config.database import ERP_DB_CONFIG
from utils.line_identifier import identify_erp_line


def get_erp_connection(wono):
    """根据工单号获取对应的ERP数据库连接(SQL Server)

    Args:
        wono: 工单号

    Returns:
        pymssql.Connection: 数据库连接对象
    """
    erp_line = identify_erp_line(wono)
    config = ERP_DB_CONFIG[erp_line]
    return pymssql.connect(
        server=config['server'],
        user=config['user'],
        password=config['password'],
        database=config['database']
    )

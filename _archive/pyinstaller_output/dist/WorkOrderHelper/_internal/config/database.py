# -*- coding: utf-8 -*-
"""数据库配置"""

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

# iplant_web用户配置（用于查询工单计划数量）
IPLANT_WEB_CONFIG = {
    'user': 'iplant_web',
    'password': 'iplant'
}

# EAI服务器配置
EAI_SERVER = {
    'host': '172.17.10.163',
    'port': 2200,
    'user': 'root',
    'password': 'Hangqu123',
    'log_path': '/var/eai/logs/'
}

# EAI日志文件映射（根据产线）- 报工日志（ACC→ERP）
EAI_LOG_FILES = {
    'dpeps1': 'FLOW_DP-EPS\\IPA MES报工接口.log',
    'smt2': 'FLOW_SMT\\MID-Line2MES报工接口.log',
    'dpepp1': 'FLOW_DP-SMT\\MID\\EPP MES报工接口.log',
}

# EAI下达工单日志文件映射（ERP→MES）- 旧版按产线分开
EAI_ISSUE_LOG_FILES = {
    'dpeps1': 'FLOW_DP-EPS\\IPA MES工单接口.log',
    'smt2': 'FLOW_SMT\\MID-Line2MES工单接口.log',
    'dpepp1': 'FLOW_DP-SMT\\MID\\EPP MES工单接口.log',
}

# EAI下达工单日志文件（新版 - 统一日志文件）
EAI_ISSUE_LOG_FILE_NEW = 'FLOW_ERP发送到MES接口.log'

# HULU Redis配置
HULU_REDIS_HOST = "172.17.10.160"
HULU_REDIS_PORT = 6379

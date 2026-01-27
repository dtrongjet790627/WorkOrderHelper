# -*- mode: python ; coding: utf-8 -*-
"""
WorkOrderHelper PyInstaller Spec File
ACC工单管理系统打包配置
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

# 项目根目录
project_root = r'D:\TechTeam\Delivery\ACC运维\2025-12-28_ERP收货不足处理\web_app'

block_cipher = None

# 需要包含的数据文件和目录
datas = [
    # 模板目录
    (os.path.join(project_root, 'templates'), 'templates'),
    # 静态文件目录
    (os.path.join(project_root, 'static'), 'static'),
    # 配置目录
    (os.path.join(project_root, 'config'), 'config'),
]

# 添加paramiko等包的元数据（解决PackageNotFoundError）
datas += copy_metadata('paramiko')
datas += copy_metadata('bcrypt')
datas += copy_metadata('cryptography')
datas += copy_metadata('cffi')

# 隐式导入的模块（PyInstaller可能无法自动检测的模块）
hiddenimports = [
    # Flask相关
    'flask',
    'flask.json',
    'jinja2',
    'werkzeug',
    'werkzeug.routing',
    'werkzeug.serving',
    'werkzeug.exceptions',
    'werkzeug.datastructures',
    'click',

    # 数据库驱动
    'cx_Oracle',
    'pymssql',

    # 数据处理
    'pandas',
    'numpy',
    'openpyxl',

    # SSH相关
    'paramiko',
    'cryptography',
    'bcrypt',
    'nacl',

    # 项目路由模块
    'routes',
    'routes.workorder',
    'routes.packing',
    'routes.erp',
    'routes.eai_logs',
    'routes.hulu',
    'routes.debug',
    'routes.detail_query',
    'routes.auth',
    'routes.logs',

    # 项目工具模块
    'utils',
    'utils.logger',
    'utils.license',
    'utils.ssh_helper',
    'utils.line_identifier',
    'utils.permission',
    'utils.log_parser',
    'utils.operation_log',

    # 项目模型模块
    'models',
    'models.acc_db',
    'models.erp_db',

    # 项目配置模块
    'config',
    'config.settings',
    'config.database',
]

a = Analysis(
    [os.path.join(project_root, 'app_server.py')],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'PIL',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WorkOrderHelper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 保持控制台窗口以便查看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'static', 'images', 'favicon.png') if os.path.exists(os.path.join(project_root, 'static', 'images', 'favicon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WorkOrderHelper',
)

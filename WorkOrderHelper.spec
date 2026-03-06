# -*- mode: python ; coding: utf-8 -*-
"""
WorkOrderHelper PyInstaller Spec File
ACC工单管理系统打包配置

使用方法：
    cd web_app目录
    pyinstaller WorkOrderHelper.spec --clean

输出目录：dist/WorkOrderHelper/
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

# 项目根目录（spec文件所在目录）
project_root = os.path.dirname(os.path.abspath(SPEC))

block_cipher = None

# 需要包含的数据文件和目录
# 注意：routes/utils/models/config 是Python模块，由PyInstaller通过hiddenimports自动打包
# templates/static/config 放在exe同级目录（外部），不打包进_internal
datas = []

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
    'jinja2.ext',
    'werkzeug',
    'werkzeug.routing',
    'werkzeug.serving',
    'werkzeug.exceptions',
    'werkzeug.datastructures',
    'click',
    'itsdangerous',

    # 数据库驱动 - oracledb（替代cx_Oracle）
    'oracledb',
    'oracledb.thick_impl',
    'oracledb.thin_impl',
    'oracledb.errors',
    'oracledb.base_impl',
    'pymssql',

    # 数据处理
    'pandas',
    'numpy',
    'openpyxl',

    # SSH相关
    'paramiko',
    'paramiko.transport',
    'paramiko.auth_handler',
    'paramiko.sftp_client',
    'cryptography',
    'cryptography.hazmat.primitives.ciphers.algorithms',
    'cryptography.hazmat.backends.openssl',
    'bcrypt',
    'nacl',
    'nacl.bindings',

    # Redis
    'redis',
    'redis.client',
    'redis.connection',

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
    'utils.operation_log',
    'utils.deployment',
    'utils.log_parser',

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
    [os.path.join(project_root, 'app.py')],
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

# -*- coding: utf-8 -*-
"""
工单小管家 - 部署打包脚本（简化版）

功能：
- 复制源码到独立的release目录
- 排除license生成工具（scripts目录）
- 排除开发相关文件

用法：
    python deploy_release.py

输出目录：
    release/工单小管家_V2.1_YYYYMMDD/
"""

import os
import shutil
from datetime import datetime

# 配置
SOURCE_DIR = os.path.join(os.path.dirname(__file__), 'web_app')
BASE_RELEASE_DIR = os.path.join(os.path.dirname(__file__), 'release')
APP_NAME = '工单小管家'
VERSION = 'V2.1'

# 排除的目录
EXCLUDE_DIRS = [
    'scripts',           # License生成工具
    '__pycache__',       # Python缓存
    '.git',              # Git目录
    'venv',              # 虚拟环境
    '.idea',             # IDE配置
    'build',             # 构建目录
    'dist',              # 分发目录
]

# 排除的文件
EXCLUDE_FILES = [
    'generate_license.py',   # License生成脚本
    '*.pyc',                 # 编译文件
    '*.pyo',
    '*.log',                 # 日志文件
    '.gitignore',
    '.env',
    'server_pid',
    'nul',
]

# 排除的文件扩展名
EXCLUDE_EXTENSIONS = ['.pyc', '.pyo', '.log', '.bak']


def should_exclude(name, is_dir=False):
    """判断是否应该排除"""
    if is_dir:
        return name in EXCLUDE_DIRS

    # 检查文件名
    if name in EXCLUDE_FILES:
        return True

    # 检查扩展名
    _, ext = os.path.splitext(name)
    if ext in EXCLUDE_EXTENSIONS:
        return True

    # 检查通配符匹配
    for pattern in EXCLUDE_FILES:
        if pattern.startswith('*') and name.endswith(pattern[1:]):
            return True

    return False


def copy_tree_filtered(src, dst):
    """过滤复制目录树"""
    os.makedirs(dst, exist_ok=True)

    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if os.path.isdir(s):
            if not should_exclude(item, is_dir=True):
                copy_tree_filtered(s, d)
        else:
            if not should_exclude(item, is_dir=False):
                shutil.copy2(s, d)


def create_start_scripts(release_dir):
    """创建启动脚本"""

    # Windows启动脚本
    start_bat = f'''@echo off
chcp 65001 >nul
title {APP_NAME}
cd /d "%~dp0"

echo ========================================
echo   {APP_NAME} {VERSION}
echo ========================================
echo.
echo 正在启动服务...
echo 访问地址: http://127.0.0.1:5003
echo.
echo 按 Ctrl+C 停止服务
echo ========================================
echo.

python app_server.py
pause
'''

    with open(os.path.join(release_dir, 'start.bat'), 'w', encoding='utf-8') as f:
        f.write(start_bat)

    # 后台启动脚本
    start_bg_bat = f'''@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在后台启动 {APP_NAME}...
start /B pythonw app_server.py
echo 服务已启动
echo 访问地址: http://127.0.0.1:5003
timeout /t 3
'''

    with open(os.path.join(release_dir, 'start_background.bat'), 'w', encoding='utf-8') as f:
        f.write(start_bg_bat)

    # 停止脚本
    stop_bat = f'''@echo off
chcp 65001 >nul
echo 正在停止 {APP_NAME}...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5003 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
)
echo 服务已停止
pause
'''

    with open(os.path.join(release_dir, 'stop.bat'), 'w', encoding='utf-8') as f:
        f.write(stop_bat)


def create_readme(release_dir):
    """创建说明文件"""

    readme = f'''# {APP_NAME} {VERSION}

## 环境要求

- Python 3.8+
- 依赖包: flask, cx_Oracle, pymssql, pandas, paramiko, redis

安装依赖:
```
pip install -r requirements.txt
```

## 使用方法

1. **启动服务**: 双击 `start.bat`
2. **后台启动**: 双击 `start_background.bat`
3. **停止服务**: 双击 `stop.bat` 或按 Ctrl+C
4. **访问地址**: http://127.0.0.1:5003

## 目录说明

| 目录/文件 | 说明 |
|-----------|------|
| config/ | 配置文件 |
| templates/ | HTML模板 |
| static/ | 静态资源(CSS/JS/图片) |
| routes/ | 路由模块 |
| utils/ | 工具模块 |
| models/ | 数据模型 |
| logs/ | 运行日志(自动生成) |
| license.lic | 授权文件 |
| app_server.py | 主程序入口 |

## 授权说明

- 需要有效的 `license.lic` 文件
- 授权过期后在界面输入新授权码即可

## 配置修改

- 数据库: `config/database.py`
- 系统设置: `config/settings.py`

---
部署时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
'''

    with open(os.path.join(release_dir, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)


def main():
    # 生成发布目录名
    date_str = datetime.now().strftime('%Y%m%d')
    release_name = f'{APP_NAME}_{VERSION}_{date_str}'
    release_dir = os.path.join(BASE_RELEASE_DIR, release_name)

    print('=' * 50)
    print(f'  {APP_NAME} 部署打包工具')
    print('=' * 50)
    print(f'源码目录: {SOURCE_DIR}')
    print(f'发布目录: {release_dir}')
    print()

    # 清理已存在的目录
    if os.path.exists(release_dir):
        print(f'清理已存在的目录...')
        shutil.rmtree(release_dir)

    # 创建发布目录
    os.makedirs(BASE_RELEASE_DIR, exist_ok=True)

    # 复制文件
    print('复制文件...')
    copy_tree_filtered(SOURCE_DIR, release_dir)

    # 确保logs目录存在
    os.makedirs(os.path.join(release_dir, 'logs'), exist_ok=True)

    # 创建启动脚本
    print('创建启动脚本...')
    create_start_scripts(release_dir)

    # 创建说明文件
    print('创建说明文件...')
    create_readme(release_dir)

    # 统计文件
    file_count = 0
    dir_count = 0
    total_size = 0

    for root, dirs, files in os.walk(release_dir):
        dir_count += len(dirs)
        for f in files:
            file_count += 1
            total_size += os.path.getsize(os.path.join(root, f))

    print()
    print('=' * 50)
    print('  打包完成!')
    print('=' * 50)
    print(f'发布目录: {release_dir}')
    print(f'文件数量: {file_count}')
    print(f'目录数量: {dir_count}')
    print(f'总大小: {total_size / 1024 / 1024:.2f} MB')
    print()
    print('排除的内容:')
    for d in EXCLUDE_DIRS:
        print(f'  - {d}/')
    print()
    print('下一步:')
    print(f'  1. 将 {release_dir} 复制到目标服务器')
    print('  2. 安装Python依赖: pip install -r requirements.txt')
    print('  3. 运行 start.bat 启动服务')


if __name__ == '__main__':
    main()

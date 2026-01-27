# -*- coding: utf-8 -*-
"""
工单小管家 - 安全版本打包脚本 V2.0

改进：
- 源码打包进exe，不暴露.py文件
- 使用 onedir 模式以支持 templates/static 热更新
- _internal 目录只保留必要的 dll/pyd，删除所有 .py 文件
- 外部保留: config/, templates/, static/, logs/, license.lic

用法：
    python build_release.py

输出目录结构：
    release/
    ├── 工单小管家.exe        # 主程序（源码已编译进内部）
    ├── _internal/           # 运行时依赖（只有dll/pyd，无.py源码）
    ├── config/              # 配置文件（可修改）
    ├── templates/           # 模板文件
    ├── static/              # 静态资源
    ├── license.lic          # 授权文件
    ├── logs/                # 日志目录
    └── start.bat            # 启动脚本
"""

import os
import sys
import shutil
import subprocess
from datetime import datetime

# 配置
SOURCE_DIR = os.path.join(os.path.dirname(__file__), 'web_app')
RELEASE_DIR = os.path.join(os.path.dirname(__file__), 'release')
MAIN_SCRIPT = 'app_server.py'
APP_NAME = '工单小管家'

# 需要复制到外部的目录（便于用户修改）
EXTERNAL_DIRS = ['config', 'templates', 'static']

# 需要复制到外部的文件
EXTERNAL_FILES = ['license.lic']

# 排除的目录（不参与打包）
EXCLUDE_DIRS = ['scripts', '__pycache__', '.git', 'logs', 'venv', 'build', 'dist']


def clean_release_dir():
    """清理发布目录"""
    if os.path.exists(RELEASE_DIR):
        print(f"清理旧的发布目录: {RELEASE_DIR}")
        shutil.rmtree(RELEASE_DIR)
    os.makedirs(RELEASE_DIR)
    print(f"创建发布目录: {RELEASE_DIR}")


def build_exe():
    """使用PyInstaller打包 - 源码编译进exe"""
    print("\n" + "=" * 50)
    print("  开始打包（源码保护模式）")
    print("=" * 50)

    main_script_path = os.path.join(SOURCE_DIR, MAIN_SCRIPT)

    # 收集项目内部的Python模块（不包含外部资源）
    # 这些会被编译成.pyc打包进exe
    internal_modules = ['config', 'models', 'routes', 'utils']

    # 构建 --add-data 参数（将资源打包进exe内部）
    add_data_args = []

    # templates 和 static 打包进exe内部，同时也复制到外部
    # 这样程序优先使用外部的（支持热更新），没有外部的就用内部打包的
    for res_dir in ['templates', 'static']:
        res_path = os.path.join(SOURCE_DIR, res_dir)
        if os.path.exists(res_path):
            # 注意Windows路径用分号
            add_data_args.append(f'--add-data={res_path};{res_dir}')

    # PyInstaller命令 - 使用 onedir 模式
    # 使用 python -m PyInstaller 确保正确调用
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onedir',                               # 文件夹模式（支持外部资源）
        '--noconsole',                            # 无控制台窗口
        f'--name={APP_NAME}',                     # 输出名称
        f'--distpath={RELEASE_DIR}',              # 输出目录
        '--clean',                                # 清理临时文件
        f'--workpath={os.path.join(RELEASE_DIR, "build")}',  # 临时目录
        f'--specpath={RELEASE_DIR}',              # spec文件目录

        # 排除不需要的模块
        '--exclude-module=scripts',
        '--exclude-module=generate_license',
        '--exclude-module=tkinter',               # 不需要GUI
        '--exclude-module=matplotlib',            # 不需要绑图
        '--exclude-module=PIL',                   # 不需要图像处理

        # 隐藏导入（确保这些模块被打包）
        '--hidden-import=flask',
        '--hidden-import=jinja2',
        '--hidden-import=cx_Oracle',
        '--hidden-import=pymssql',
        '--hidden-import=pandas',
        '--hidden-import=paramiko',
        '--hidden-import=redis',
        '--hidden-import=config',
        '--hidden-import=config.settings',
        '--hidden-import=config.database',
        '--hidden-import=models',
        '--hidden-import=models.acc_db',
        '--hidden-import=models.erp_db',
        '--hidden-import=routes',
        '--hidden-import=routes.auth',
        '--hidden-import=routes.erp',
        '--hidden-import=routes.debug',
        '--hidden-import=routes.eai_logs',
        '--hidden-import=routes.detail_query',
        '--hidden-import=routes.workorder',
        '--hidden-import=routes.hulu',
        '--hidden-import=routes.packing',
        '--hidden-import=routes.logs',
        '--hidden-import=utils',
        '--hidden-import=utils.license',
        '--hidden-import=utils.logger',
        '--hidden-import=utils.ssh_helper',
        '--hidden-import=utils.line_identifier',
        '--hidden-import=utils.permission',
        '--hidden-import=utils.log_parser',
        '--hidden-import=utils.operation_log',

        # 收集子模块
        '--collect-submodules=routes',
        '--collect-submodules=models',
        '--collect-submodules=utils',
        '--collect-submodules=config',
    ]

    # 添加资源数据
    cmd.extend(add_data_args)

    # 添加主脚本
    cmd.append(main_script_path)

    print(f"\n执行命令:")
    print(' '.join(cmd[:10]) + ' ...')

    # 切换到源码目录执行打包
    result = subprocess.run(cmd, cwd=SOURCE_DIR)

    if result.returncode != 0:
        print("\n打包失败!")
        return False

    # 清理build目录和spec文件
    build_dir = os.path.join(RELEASE_DIR, 'build')
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    spec_file = os.path.join(RELEASE_DIR, f'{APP_NAME}.spec')
    if os.path.exists(spec_file):
        os.remove(spec_file)

    print("\nPyInstaller 打包完成!")
    return True


def remove_source_files():
    """删除 _internal 目录中的 .py 源码文件"""
    print("\n" + "=" * 50)
    print("  清理源码文件（安全处理）")
    print("=" * 50)

    internal_dir = os.path.join(RELEASE_DIR, APP_NAME, '_internal')
    if not os.path.exists(internal_dir):
        print("  警告: _internal目录不存在")
        return

    removed_count = 0
    removed_files = []

    # 遍历_internal目录，删除所有.py文件
    for root, dirs, files in os.walk(internal_dir):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                # 获取相对路径用于显示
                rel_path = os.path.relpath(file_path, internal_dir)

                # 保留某些第三方库的.py文件（如果需要）
                # 这里我们删除所有项目源码（config/models/routes/utils）
                if rel_path.startswith(('config', 'models', 'routes', 'utils')):
                    try:
                        os.remove(file_path)
                        removed_files.append(rel_path)
                        removed_count += 1
                    except Exception as e:
                        print(f"  警告: 无法删除 {rel_path}: {e}")

    print(f"  删除了 {removed_count} 个项目源码文件:")
    for f in removed_files[:10]:
        print(f"    - {f}")
    if len(removed_files) > 10:
        print(f"    ... 以及其他 {len(removed_files) - 10} 个文件")

    # 删除空目录
    for dir_name in ['config', 'models', 'routes', 'utils']:
        dir_path = os.path.join(internal_dir, dir_name)
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                print(f"  删除目录: {dir_name}/")
            except Exception as e:
                print(f"  警告: 无法删除目录 {dir_name}/: {e}")


def copy_external_resources():
    """复制外部资源文件"""
    print("\n" + "=" * 50)
    print("  复制外部资源")
    print("=" * 50)

    # 目标目录（exe所在目录）
    app_dir = os.path.join(RELEASE_DIR, APP_NAME)

    # 复制目录
    for dir_name in EXTERNAL_DIRS:
        src = os.path.join(SOURCE_DIR, dir_name)
        dst = os.path.join(app_dir, dir_name)
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            # 统计文件数
            file_count = sum(len(files) for _, _, files in os.walk(dst))
            print(f"  复制目录: {dir_name}/ ({file_count} 个文件)")

    # 复制文件
    for file_name in EXTERNAL_FILES:
        src = os.path.join(SOURCE_DIR, file_name)
        dst = os.path.join(app_dir, file_name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  复制文件: {file_name}")

    # 创建logs目录
    logs_dir = os.path.join(app_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    print(f"  创建目录: logs/")


def create_start_script():
    """创建启动脚本"""
    print("\n" + "=" * 50)
    print("  创建启动脚本")
    print("=" * 50)

    app_dir = os.path.join(RELEASE_DIR, APP_NAME)

    # Windows批处理启动脚本
    bat_content = f'''@echo off
chcp 65001 >nul
title {APP_NAME}
echo ========================================
echo   {APP_NAME} 启动中...
echo ========================================
echo.

cd /d "%~dp0"
start "" "{APP_NAME}.exe"

echo 程序已启动，请在浏览器中访问:
echo   http://127.0.0.1:5003
echo.
echo 按任意键关闭此窗口...
pause >nul
'''

    bat_path = os.path.join(app_dir, 'start.bat')
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat_content)
    print(f"  创建: start.bat")

    # 创建停止脚本
    stop_content = f'''@echo off
chcp 65001 >nul
echo 正在停止 {APP_NAME}...
taskkill /F /IM "{APP_NAME}.exe" 2>nul
if %errorlevel%==0 (
    echo 程序已停止
) else (
    echo 程序未在运行
)
pause
'''

    stop_path = os.path.join(app_dir, 'stop.bat')
    with open(stop_path, 'w', encoding='utf-8') as f:
        f.write(stop_content)
    print(f"  创建: stop.bat")


def create_readme():
    """创建说明文件"""
    app_dir = os.path.join(RELEASE_DIR, APP_NAME)

    readme_content = f'''# {APP_NAME} V2.1

## 文件说明

| 文件/目录 | 说明 |
|-----------|------|
| {APP_NAME}.exe | 主程序 |
| _internal/ | 运行时依赖（请勿修改） |
| start.bat | 启动脚本 |
| stop.bat | 停止脚本 |
| config/ | 配置文件目录 |
| templates/ | 页面模板目录 |
| static/ | 静态资源目录 |
| logs/ | 日志目录 |
| license.lic | 授权文件 |

## 使用方法

1. 双击 `start.bat` 启动程序
2. 浏览器访问 http://127.0.0.1:5003
3. 双击 `stop.bat` 停止程序

## 授权说明

- 程序需要有效的 `license.lic` 文件才能运行
- 授权过期后需要获取新的授权码
- 授权码通过程序界面输入即可激活

## 配置修改

- 数据库配置: `config/database.py`
- 系统配置: `config/settings.py`

## 注意事项

- 请勿删除或移动程序文件
- 请勿修改 _internal 目录内容
- 日志文件保存在 logs/ 目录下
- 如有问题请联系管理员

---
打包时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
'''

    readme_path = os.path.join(app_dir, 'README.md')
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"  创建: README.md")


def verify_result():
    """验证打包结果"""
    print("\n" + "=" * 50)
    print("  验证打包结果")
    print("=" * 50)

    app_dir = os.path.join(RELEASE_DIR, APP_NAME)
    internal_dir = os.path.join(app_dir, '_internal')

    # 检查是否还有.py源码
    py_files = []
    for root, dirs, files in os.walk(internal_dir):
        for file in files:
            if file.endswith('.py'):
                rel_path = os.path.relpath(os.path.join(root, file), internal_dir)
                # 只关注项目源码目录
                if rel_path.startswith(('config', 'models', 'routes', 'utils')):
                    py_files.append(rel_path)

    if py_files:
        print(f"  [警告] _internal 中仍有 {len(py_files)} 个项目源码文件:")
        for f in py_files[:5]:
            print(f"    - {f}")
        return False
    else:
        print("  [OK] _internal 中无项目源码文件")

    # 检查关键文件
    key_files = [
        f'{APP_NAME}.exe',
        'start.bat',
        'stop.bat',
        'config/settings.py',
        'templates/index_hulu.html',
    ]

    missing = []
    for f in key_files:
        if not os.path.exists(os.path.join(app_dir, f)):
            missing.append(f)

    if missing:
        print(f"  [警告] 缺少文件:")
        for f in missing:
            print(f"    - {f}")
        return False
    else:
        print("  [OK] 所有关键文件存在")

    return True


def print_summary():
    """打印打包结果摘要"""
    app_dir = os.path.join(RELEASE_DIR, APP_NAME)

    print("\n" + "=" * 50)
    print("  打包完成!")
    print("=" * 50)
    print(f"\n发布目录: {app_dir}")
    print("\n目录内容:")

    for item in sorted(os.listdir(app_dir)):
        item_path = os.path.join(app_dir, item)
        if os.path.isdir(item_path):
            # 统计目录大小
            size = sum(os.path.getsize(os.path.join(r, f))
                      for r, _, files in os.walk(item_path)
                      for f in files)
            print(f"  [目录] {item}/ ({size:,} bytes)")
        else:
            size = os.path.getsize(item_path)
            print(f"  [文件] {item} ({size:,} bytes)")


def main():
    print("=" * 50)
    print(f"  {APP_NAME} 安全版本打包工具 V2.0")
    print("=" * 50)
    print(f"源码目录: {SOURCE_DIR}")
    print(f"发布目录: {RELEASE_DIR}")

    # 检查PyInstaller
    try:
        import PyInstaller
        print(f"PyInstaller版本: {PyInstaller.__version__}")
    except ImportError:
        print("\n错误: 未安装PyInstaller")
        print("请执行: pip install pyinstaller")
        return 1

    # 执行打包流程
    clean_release_dir()

    if not build_exe():
        return 1

    # 删除源码文件
    remove_source_files()

    # 复制外部资源
    copy_external_resources()

    # 创建脚本
    create_start_script()
    create_readme()

    # 验证结果
    if not verify_result():
        print("\n[警告] 打包结果验证失败，请检查")

    print_summary()

    return 0


if __name__ == '__main__':
    sys.exit(main())

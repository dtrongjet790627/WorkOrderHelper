@echo off
chcp 65001 >nul
echo ====================================
echo  WorkOrderHelper 打包脚本
echo  ACC工单管理系统 PyInstaller打包
echo ====================================
echo.

:: 切换到脚本所在目录（web_app目录）
cd /d "%~dp0"

echo [1/3] 检查Python环境...
where pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到pyinstaller，请先安装：pip install pyinstaller
    pause
    exit /b 1
)

echo [2/3] 开始打包...
pyinstaller WorkOrderHelper.spec --clean

if %errorlevel% neq 0 (
    echo.
    echo [错误] 打包失败，请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo [3/3] 打包完成！
echo.
echo 输出目录：dist\WorkOrderHelper\
echo.
echo 注意事项：
echo   1. Oracle Instant Client DLL 需手动复制到 dist\WorkOrderHelper\ 目录
echo   2. 部署时设置环境变量 WO_DEPLOYMENT=165 或 WO_DEPLOYMENT=168
echo   3. license.lic 授权文件需放置在 dist\WorkOrderHelper\ 目录
echo.
pause

@echo off
echo 正在重启 ACC_WorkOrder 服务...
net stop ACC_WorkOrder
timeout /t 2 /nobreak >nul
net start ACC_WorkOrder
echo.
echo 服务已重启完成！
pause

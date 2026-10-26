@echo off
chcp 65001 >nul
setlocal

rem ===== 一键停止：按端口 8000/5173 结束后端与前端进程 =====
echo [停止] 正在结束后端 (端口 8000) 相关进程...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
  taskkill /PID %%p /T /F >nul 2>nul
)
echo [停止] 正在结束前端 (端口 5173) 相关进程...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
  taskkill /PID %%p /T /F >nul 2>nul
)
echo [停止] 清理残留的运行窗口（若存在）...
taskkill /FI "WINDOWTITLE eq Agent-Backend(8000)*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Agent-Frontend(5173)*" /F >nul 2>nul

echo.
echo [完成] 已停止后端与前端。
pause
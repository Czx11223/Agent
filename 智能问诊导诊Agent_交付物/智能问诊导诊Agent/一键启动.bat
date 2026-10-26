@echo off
chcp 65001 >nul
setlocal

rem ===== 一键启动：后端(8000) + 前端(5173)，各开独立窗口 =====
set "ROOT=%~dp0"
set "BE_PY=%ROOT%backend\.venv\Scripts\python.exe"
set "BE_CWD=%ROOT%backend"
set "FE_CWD=%ROOT%frontend"

echo [启动] 校验后端运行环境...
if not exist "%BE_PY%" (
  echo [错误] 未找到后端虚拟环境: %BE_PY%
  echo        请确认 backend\.venv 已创建（python -m venv backend\.venv 后 pip install -r requirements.txt）
  pause
  exit /b 1
)

echo [启动] 正在打开后端窗口 (端口 8000) ...
start "Agent-Backend(8000)" cmd /k "cd /d "%BE_CWD%" && ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo [启动] 正在打开前端窗口 (端口 5173) ...
start "Agent-Frontend(5173)" cmd /k "cd /d "%FE_CWD%" && npm.cmd run dev"

echo.
echo [完成] 已启动。两个窗口正在运行：
echo    前端 -> http://localhost:5173
echo    后端 -> http://127.0.0.1:8000/docs
echo.
echo 提示：若端口被占用启动失败，请先运行「一键停止.bat」再重试。
pause
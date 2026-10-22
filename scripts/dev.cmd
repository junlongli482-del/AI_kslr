@echo off
setlocal
if /I "%~1"=="api" goto api
if /I "%~1"=="ai" goto ai
if /I "%~1"=="web" goto web
if /I "%~1"=="mineru" goto mineru
if /I "%~1"=="help" goto help
if not "%~1"=="" if /I not "%~1"=="all" goto help

rem Open interactive terminals so the user can read logs and stop each service.
start "Quick Entry - Python reload" cmd /k call "%~f0" ai
start "Quick Entry - Java source" cmd /k call "%~f0" api
start "Quick Entry - Vite HMR" cmd /k call "%~f0" web
exit /b 0

:api
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-api-dev.ps1"
exit /b %errorlevel%

:ai
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-ai-dev.ps1"
exit /b %errorlevel%

:web
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-web-dev.ps1"
exit /b %errorlevel%

:mineru
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-mineru.ps1"
exit /b %errorlevel%

:help
echo Usage: scripts\dev.cmd [all^|api^|ai^|web^|mineru^|help]
echo No argument opens three interactive development terminals.
echo mineru starts the resident local MinerU server on 127.0.0.1:8020 (GPU).
echo Stop the old service before starting another on the same port.
echo Frontend: Vite HMR. Python: auto reload. Java: Ctrl+C then rerun api.
echo Database must be running. No package or full test suite on startup.
exit /b 0

@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_offline.ps1" %*
set "taskExit=%ERRORLEVEL%"
echo.
echo Press any key to close this window.
pause >nul
exit /b %taskExit%

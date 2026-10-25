@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Yeobaek - Personal Scheduler
echo.
echo Yeobaek is preparing your personal workspace.
echo First launch needs Internet access. Please keep this window open.
echo.
if not exist "web\dist\index.html" (
  echo ERROR: Extract the entire ZIP before running START-Yeobaek.cmd.
  goto failed
)
if not defined LOCALAPPDATA (
  echo ERROR: Windows user folder LOCALAPPDATA is unavailable.
  goto failed
)
set "YEObaek_ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "YEObaek_ARCH=%PROCESSOR_ARCHITEW6432%"
set "YEObaek_UV="
if /I "%YEObaek_ARCH%"=="AMD64" set "YEObaek_UV=%~dp0tools\x64\uv.exe"
if /I "%YEObaek_ARCH%"=="ARM64" set "YEObaek_UV=%~dp0tools\x64\uv.exe"
if not defined YEObaek_UV (
  echo ERROR: This package requires 64-bit Windows 10 or 11.
  goto failed
)
if not exist "%YEObaek_UV%" (
  echo ERROR: uv.exe is missing. Extract the entire ZIP again.
  goto failed
)
set "UV_CACHE_DIR=%LOCALAPPDATA%\Yeobaek\cache"
set "UV_PYTHON_INSTALL_DIR=%LOCALAPPDATA%\Yeobaek\runtime\python"
set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\Yeobaek\runtime\venv-0.2.7"
set "SCHEDULER_DB=%LOCALAPPDATA%\Yeobaek\data\scheduler.sqlite3"
set "SCHEDULER_ORIGIN="
set "PYTHONUTF8=1"
"%YEObaek_UV%" sync --frozen --no-build --no-dev --no-install-project --managed-python --python 3.12
if errorlevel 1 goto failed
echo.
echo Your browser will open when the app is ready.
echo Keep this window open while using Yeobaek. Close it to stop.
"%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" -m backend.desktop
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo Startup failed. Please share the error message above in the Codex chat.
echo Do not delete your data folder while troubleshooting.
pause
exit /b 1

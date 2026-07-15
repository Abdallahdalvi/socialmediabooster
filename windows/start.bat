@echo off
setlocal
title YT Views Booster

set ROOT=%~dp0..
set BACKEND=%ROOT%\backend
set TOR_DIR=%ROOT%\tor

REM --- Start Tor in a background window ----------------------------------
if not exist "%TOR_DIR%\tor.exe" (
    echo [ERROR] Tor binary not found at %TOR_DIR%\tor.exe
    echo         Run install.bat first, or install Tor Expert Bundle manually.
    pause & exit /b 1
)
tasklist /FI "IMAGENAME eq tor.exe" 2>nul | find /I "tor.exe" >nul
if errorlevel 1 (
    echo [i] Launching Tor...
    start "" /min "%TOR_DIR%\tor.exe" -f "%TOR_DIR%\torrc"
    timeout /t 8 /nobreak >nul
)

REM --- Start backend (which also serves the built frontend on the same port)
pushd "%BACKEND%"
call .venv\Scripts\activate.bat
if not exist "data" mkdir data

echo.
echo ============================================================
echo   YT Views Booster running at:  http://localhost:8001
echo   Close this window to stop.
echo ============================================================
echo.

REM Open the app in the default browser after backend has booted
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8001"

python -m uvicorn server:app --host 127.0.0.1 --port 8001
popd
endlocal

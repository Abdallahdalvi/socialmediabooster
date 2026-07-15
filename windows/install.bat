@echo off
setlocal enabledelayedexpansion
title YT Views Booster - Installer

echo.
echo ============================================================
echo   YT Views Booster - Windows Installer (one-time setup)
echo ============================================================
echo.

REM ----- 1. Preconditions -----------------------------------------------------
where python >nul 2>&1 || (
    echo [ERROR] Python is not installed or not on PATH.
    echo         Install Python 3.11+ from https://python.org/downloads
    echo         and tick "Add Python to PATH".
    pause & exit /b 1
)

where node >nul 2>&1 || (
    echo [ERROR] Node.js is not installed or not on PATH.
    echo         Install Node 20+ from https://nodejs.org
    pause & exit /b 1
)

where yarn >nul 2>&1 || (
    echo [i] Installing yarn globally...
    call npm install -g yarn || ( echo [ERROR] yarn install failed. & pause & exit /b 1 )
)

REM ----- 2. Backend venv + deps ----------------------------------------------
pushd "%~dp0..\backend"
if not exist ".venv" (
    echo [i] Creating Python virtual environment...
    python -m venv .venv || ( echo [ERROR] venv creation failed & popd & pause & exit /b 1 )
)

call .venv\Scripts\activate.bat
echo [i] Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install stem aiosqlite pysocks "requests[socks]" playwright pyinstaller
python -m playwright install chromium
if errorlevel 1 ( echo [ERROR] Python deps failed & popd & pause & exit /b 1 )
popd

REM ----- 3. Frontend build ----------------------------------------------------
pushd "%~dp0..\frontend"
if not exist ".env" (
    echo REACT_APP_BACKEND_URL= > .env
)
echo [i] Installing frontend deps...
call yarn install --silent
echo [i] Building React production bundle...
call yarn build
if errorlevel 1 ( echo [ERROR] Frontend build failed & popd & pause & exit /b 1 )
popd

REM ----- 4. Copy build into backend for embedded serving ---------------------
echo [i] Bundling frontend into backend...
if exist "%~dp0..\backend\static" rmdir /s /q "%~dp0..\backend\static"
xcopy /e /i /q "%~dp0..\frontend\build" "%~dp0..\backend\static" >nul

REM ----- 5. Tor Expert Bundle -------------------------------------------------
set TOR_DIR=%~dp0..\tor
if not exist "%TOR_DIR%\tor.exe" (
    echo [i] Downloading Tor Expert Bundle...
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://archive.torproject.org/tor-package-archive/torbrowser/13.5.7/tor-expert-bundle-windows-x86_64-13.5.7.tar.gz' -OutFile '$env:TEMP\tor-expert.tgz'"
    if errorlevel 1 (
        echo [WARN] Automatic download failed. Please install Tor Expert Bundle manually
        echo        from https://www.torproject.org/download/tor/ and extract into %TOR_DIR%
    ) else (
        if not exist "%TOR_DIR%" mkdir "%TOR_DIR%"
        tar -xzf "%TEMP%\tor-expert.tgz" -C "%TOR_DIR%" 2>nul
        REM Tor expert bundle usually extracts into ./tor/ subfolder — flatten it
        if exist "%TOR_DIR%\tor\tor.exe" (
            xcopy /e /i /q "%TOR_DIR%\tor\*" "%TOR_DIR%\" >nul
            rmdir /s /q "%TOR_DIR%\tor"
        )
    )
)

REM ----- 6. Write torrc & data folder -----------------------------------------
if not exist "%TOR_DIR%\data" mkdir "%TOR_DIR%\data"
(
    echo SocksPort 9050
    echo ControlPort 9051
    echo CookieAuthentication 1
    echo DataDirectory %TOR_DIR%\data
    echo Log notice file %TOR_DIR%\notice.log
    echo ExitPolicy reject *:*
) > "%TOR_DIR%\torrc"

REM ----- 7. Write backend .env if missing ------------------------------------
if not exist "%~dp0..\backend\.env" (
    (
        echo CORS_ORIGINS=*
        echo BROWSER_MODE=playwright
        echo TOR_SOCKS=socks5://127.0.0.1:9050
        echo TOR_CONTROL_PORT=9051
        echo ROTATION_INTERVAL=3
        echo LOG_RETENTION_DAYS=7
        echo SQLITE_PATH=%~dp0..\backend\data\yt_booster.db
    ) > "%~dp0..\backend\.env"
)

echo.
echo ============================================================
echo   INSTALL COMPLETE  --  double-click start.bat to launch
echo ============================================================
echo.
pause
endlocal

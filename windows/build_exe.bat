@echo off
setlocal
title YT Views Booster - Build EXE

REM Bundles server.py + local_storage.py + browser_runner.py + static frontend
REM into a single dist\yt_booster.exe using PyInstaller.
REM
REM NOTE: Playwright's Chromium and Tor are NOT bundled into the EXE
REM       (too large, and Chromium is version-pinned) — they stay in
REM       the folder next to the EXE.

set ROOT=%~dp0..
pushd "%ROOT%\backend"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Backend venv missing. Run install.bat first.
    popd & pause & exit /b 1
)
call .venv\Scripts\activate.bat

if not exist "static\index.html" (
    echo [ERROR] Frontend build missing. Run install.bat first.
    popd & pause & exit /b 1
)

echo [i] Building single-file executable with PyInstaller...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --name yt_booster ^
    --add-data "static;static" ^
    --hidden-import "aiosqlite" ^
    --hidden-import "stem" ^
    --hidden-import "stem.control" ^
    --hidden-import "playwright.async_api" ^
    --collect-all "playwright" ^
    server.py

if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    popd & pause & exit /b 1
)

echo.
echo ============================================================
echo   EXE built at:  %ROOT%\backend\dist\yt_booster.exe
echo   Copy it to the project root next to tor\ + start.bat
echo   before running.
echo ============================================================
popd
pause
endlocal

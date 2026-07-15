@echo off
REM ============================================================
REM YT Views Booster - Native EXE Builder
REM Builds a standalone Windows executable with embedded Python,
REM Tor, Node, and all dependencies
REM ============================================================

setlocal enabledelayedexpansion
title YT Views Booster - EXE Builder

echo.
echo ============================================================
echo   YT Views Booster - Building Native Windows EXE
echo ============================================================
echo.

set ROOT=%~dp0..
set BACKEND=%ROOT%\backend
set FRONTEND=%ROOT%\frontend
set ELECTRON=%ROOT%\electron-app
set DIST=%ELECTRON%\dist

REM Check prerequisites
echo [*] Checking prerequisites...
where python >nul 2>&1 || (echo [ERROR] Python not found & pause & exit /b 1)
where node >nul 2>&1 || (echo [ERROR] Node.js not found & pause & exit /b 1)
where yarn >nul 2>&1 || (echo [ERROR] Yarn not found. Run: npm install -g yarn & pause & exit /b 1)

echo [+] All prerequisites found
echo.

REM Step 1: Build backend
echo [1/5] Building backend...
pushd "%BACKEND%"
if not exist ".venv" (
    echo [i] Creating Python venv...
    python -m venv .venv
    if errorlevel 1 (echo [ERROR] venv creation failed & popd & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip setuptools wheel
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (echo [ERROR] Backend deps failed & popd & pause & exit /b 1)
popd
echo [+] Backend ready
echo.

REM Step 2: Build frontend
echo [2/5] Building frontend...
pushd "%FRONTEND%"
if not exist "node_modules" (
    echo [i] Installing frontend deps (first time, may take 2-3 min)...
    call yarn install --network-timeout 300000
    if errorlevel 1 (echo [ERROR] Yarn install failed & popd & pause & exit /b 1)
)
echo [i] Building React production bundle...
set "CI=false"
set "DISABLE_ESLINT_PLUGIN=true"
set "GENERATE_SOURCEMAP=false"
call yarn build
if errorlevel 1 (echo [ERROR] Frontend build failed & popd & pause & exit /b 1)
popd
echo [+] Frontend built
echo.

REM Step 3: Prepare Electron app
echo [3/5] Preparing Electron app...
if not exist "%ELECTRON%" mkdir "%ELECTRON%"
pushd "%ELECTRON%"
if not exist "node_modules" (
    echo [i] Installing Electron dependencies...
    call npm install --quiet electron electron-builder
    if errorlevel 1 (echo [ERROR] Electron install failed & popd & pause & exit /b 1)
)
popd
echo [+] Electron ready
echo.

REM Step 4: Copy frontend build to Electron
echo [4/5] Bundling frontend into Electron app...
if exist "%ELECTRON%\public" rmdir /s /q "%ELECTRON%\public"
mkdir "%ELECTRON%\public"
xcopy /e /i /q "%FRONTEND%\build" "%ELECTRON%\public" >nul
echo [+] Frontend bundled
echo.

REM Step 5: Build EXE with electron-builder
echo [5/5] Building Windows installer and portable EXE...
pushd "%ELECTRON%"
echo [i] This may take 2-3 minutes...
call npm run build >nul 2>&1
if errorlevel 1 (
    echo [WARN] electron-builder had issues. Trying alternative...
    call npx electron-builder
    if errorlevel 1 (echo [ERROR] Build failed & popd & pause & exit /b 1)
)
popd

echo.
echo ============================================================
echo   BUILD COMPLETE!
echo ============================================================
echo.
echo [+] Output files in: %DIST%
echo.
echo Available installers:
echo   - YTViewsBooster*.exe (installer with shortcuts)
echo   - YTViewsBooster*.portable.exe (portable, no install needed)
echo.
echo To distribute, upload the .exe file(s) to GitHub Releases.
echo.
pause
endlocal

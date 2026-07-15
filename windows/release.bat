@echo off
REM ============================================================
REM GitHub Release Uploader
REM Automatically uploads built EXE to GitHub Releases
REM Requires: GitHub CLI (gh) installed and authenticated
REM ============================================================

setlocal enabledelayedexpansion
title YT Views Booster - GitHub Release Upload

echo.
echo ============================================================
echo   YT Views Booster - GitHub Release Upload
echo ============================================================
echo.

where gh >nul 2>&1 || (
    echo [ERROR] GitHub CLI not found. Install from: https://cli.github.com/
    pause & exit /b 1
)

set ROOT=%~dp0..
set DIST=%ROOT%\electron-app\dist
set VERSION=2.0.0

echo [*] Creating GitHub release v%VERSION%...
echo.

REM Find EXE files
if not exist "%DIST%" (
    echo [ERROR] Build output not found at: %DIST%
    echo        Run build_exe.bat first
    pause & exit /b 1
)

echo [i] Found EXE files:
for %%f in ("%DIST%\*.exe") do (
    echo     - %%~nxf
)
echo.

echo [*] Uploading to GitHub...
REM Note: Update owner/repo as needed
gh release create v%VERSION% "%DIST%\*.exe" ^^
    --title "YT Views Booster v%VERSION%" ^^
    --notes "Parallel job execution with concurrent browser workers and native Windows app" ^^
    --draft

if errorlevel 1 (
    echo [WARN] Release creation had issues. You may need to:
    echo   1. Create release manually: https://github.com/Abdallahdalvi/socialmediabooster/releases
    echo   2. Upload EXE files from: %DIST%
) else (
    echo [+] Release created successfully!
)

echo.
pause
endlocal

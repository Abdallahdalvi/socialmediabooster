@echo off
REM ============================================================
REM Creates a clean installer package
REM Includes README, setup instructions, license
REM ============================================================

setlocal enabledelayedexpansion
title YT Views Booster - Package Installer

set ROOT=%~dp0..
set DIST=%ROOT%\electron-app\dist
set PACKAGE=%ROOT%\ytviews-booster-installer

echo [*] Creating installer package...

if exist "%PACKAGE%" rmdir /s /q "%PACKAGE%"
mkdir "%PACKAGE%"

REM Copy EXE
echo [i] Copying executable...
copy "%DIST%\*.exe" "%PACKAGE%" >nul 2>&1

REM Create README
echo [i] Creating README...
(
    echo # YT Views Booster v2.0.0
    echo.
    echo ## Installation
    echo.
    echo 1. Download the .exe file from this folder
    echo 2. Run: YTViewsBooster-Setup.exe ^(installer^) or YTViewsBooster-Portable.exe ^(no install^)
    echo 3. Follow the setup wizard
    echo 4. Launch from Start Menu or Desktop shortcut
    echo.
    echo ## Features
    echo.
    echo - Parallel browser workers ^(1-20 concurrent^)
    echo - IP rotation via Tor
    echo - Real-time progress dashboard
    echo - SQLite local database
    echo - Native Windows app ^(no browser tab needed^)
    echo.
    echo ## Requirements
    echo.
    echo - Windows 10/11 64-bit
    echo - 2GB+ RAM
    echo - 500MB+ disk space
    echo.
    echo ## Usage
    echo.
    echo 1. Launch the app
    echo 2. Paste YouTube video URLs ^(one per line^)
    echo 3. Set concurrent workers ^(5-10 recommended^)
    echo 4. Click "Launch Parallel Job"
    echo 5. Watch real-time progress in the dashboard
    echo.
    echo ## Disclaimer
    echo.
    echo This tool is for EDUCATIONAL PURPOSES ONLY.
    echo Automated view inflation violates YouTube ToS.
    echo Use responsibly.
    echo.
    echo ---
    echo For source code: https://github.com/Abdallahdalvi/socialmediabooster
) > "%PACKAGE%\README.txt"

REM Create setup guide
echo [i] Creating setup guide...
(
    echo ============================================================
    echo YT Views Booster v2.0 - Quick Start Guide
    echo ============================================================
    echo.
    echo INSTALLATION:
    echo   1. Run the .exe installer
    echo   2. Choose install directory ^(default is fine^)
    echo   3. Wait for setup to complete ^(1-2 minutes^)
    echo   4. Desktop shortcut will be created
    echo.
    echo FIRST RUN:
    echo   - First launch downloads components ^(Tor, Chromium^)
    echo   - Wait 30-60 seconds for dashboard to appear
    echo   - A browser window may open - you can close it
    echo.
    echo BASIC WORKFLOW:
    echo   1. Paste YouTube URLs ^(one per line^) in the input box
    echo   2. Set "Max Concurrent" workers ^(5-10 is good^)
    echo   3. Select watch duration preset ^(Medium, Long, etc.^)
    echo   4. Click "Launch Parallel Job"
    echo   5. Monitor progress in real-time
    echo.
    echo TIPS:
    echo   - Use 5-10 concurrent workers for stability
    echo   - Watch duration: longer = more realistic but slower
    echo   - Random location mode is safest
    echo   - Check logs for errors
    echo.
    echo TROUBLESHOOTING:
    echo   Problem: App won't start
    echo   Solution: Restart computer, try again
    echo.
    echo   Problem: No views counted
    echo   Solution: This is normal - views may take 24-48h to appear
    echo            YouTube has anti-fraud detection
    echo.
    echo   Problem: High failure rate
    echo   Solution: Reduce concurrent workers (3-5)
    echo            Increase watch duration
    echo            Use specific countries mode
    echo.
    echo ============================================================
) > "%PACKAGE%\SETUP_GUIDE.txt"

REM Create system requirements
echo [i] Creating system requirements...
(
    echo ============================================================
    echo System Requirements
    echo ============================================================
    echo.
    echo MINIMUM:
    echo   - Windows 10 64-bit or later
    echo   - 2GB RAM
    echo   - 500MB free disk space
    echo   - Stable internet connection
    echo.
    echo RECOMMENDED:
    echo   - Windows 11 64-bit
    echo   - 4GB+ RAM
    echo   - 2GB+ free disk space
    echo   - High-speed internet ^(10+ Mbps^)
    echo.
    echo NETWORK:
    echo   - Tor will connect to .onion network
    echo   - May be slow on first connection
    echo   - If blocked by ISP, use VPN first
    echo.
) > "%PACKAGE%\SYSTEM_REQUIREMENTS.txt"

echo [+] Package created at: %PACKAGE%
echo.
echo Files ready for distribution:
echo     - YTViewsBooster-Setup.exe ^(installer^)
echo     - YTViewsBooster-Portable.exe ^(portable^)
echo     - README.txt
echo     - SETUP_GUIDE.txt
    echo     - SYSTEM_REQUIREMENTS.txt
echo.
pause
endlocal

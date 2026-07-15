@echo off
REM Electron app builder for Windows
REM Creates a native Windows application bundle

echo [*] Building Electron native app...

cd /d "%~dp0.."
if not exist "electron-app" (
    echo [i] Creating electron-app directory...
    mkdir electron-app
    cd electron-app
    npm init -y
    npm install electron --save-dev
    npm install electron-builder --save-dev
) else (
    cd electron-app
)

REM Copy main.js if not exists
if not exist "main.js" (
    echo [i] Creating main.js...
    (
        echo const { app, BrowserWindow } = require('electron');
        echo const path = require('path');
        echo const { spawn } = require('child_process');
        echo.
        echo let mainWindow;
        echo let backendProcess;
        echo.
        echo function createWindow() {
        echo   mainWindow = new BrowserWindow({
        echo     width: 1400,
        echo     height: 900,
        echo     webPreferences: {
        echo       preload: path.join(__dirname, 'preload.js')
        echo     },
        echo     icon: path.join(__dirname, 'assets', 'icon.png')
        echo   });
        echo.
        echo   mainWindow.loadURL('http://localhost:8001');
        echo   mainWindow.webContents.openDevTools();
        echo }
        echo.
        echo app.on('ready', () => {
        echo   startBackend();
        echo   setTimeout(createWindow, 3000);
        echo });
        echo.
        echo app.on('window-all-closed', () => {
        echo   if (process.platform !== 'darwin') {
        echo     if (backendProcess) backendProcess.kill();
        echo     app.quit();
        echo   }
        echo });
        echo.
        echo function startBackend() {
        echo   const pythonPath = path.join(__dirname, '..', 'backend', '.venv', 'Scripts', 'python.exe');
        echo   const serverPath = path.join(__dirname, '..', 'backend', 'server_v2.py');
        echo   backendProcess = spawn(pythonPath, ['-m', 'uvicorn', 'server_v2:app', '--port', '8001'], {
        echo     cwd: path.join(__dirname, '..', 'backend')
        echo   });
        echo   console.log('Backend started');
        echo }
    ) > main.js
)

REM Update package.json to include build config
echo [i] Updating package.json...
node -e "var fs=require('fs');var pkg=JSON.parse(fs.readFileSync('package.json'));pkg.main='main.js';pkg.homepage='./';pkg.build={appId:'com.ytbooster.app',productName:'YT Views Booster',files:['main.js','preload.js','**!/node_modules/**'],win:{target:['nsis','portable']},nsis:{oneClick:false,allowToChangeInstallationDirectory:true}};fs.writeFileSync('package.json',JSON.stringify(pkg,null,2));console.log('Updated');"

echo [i] Building...
call npm run dist 2>nul || (
    echo [!] npm run dist not found, adding build script...
    node -e "var fs=require('fs');var pkg=JSON.parse(fs.readFileSync('package.json'));pkg.scripts={start:'electron .',build:'electron-builder'};fs.writeFileSync('package.json',JSON.stringify(pkg,null,2));"
    call npm run build
)

echo [+] Build complete! Check electron-app/dist/ for executable.
pause

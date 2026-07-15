const { app, BrowserWindow, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow;
let backendProcess;
let torProcess;

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function waitForBackend(maxRetries = 30) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await new Promise((resolve, reject) => {
        http.get('http://localhost:8001/api', (res) => {
          resolve(res.statusCode === 200);
        }).on('error', reject);
      });
      if (response) return true;
    } catch (e) {
      // Retry
    }
    await sleep(1000);
  }
  return false;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 950,
    minWidth: 1000,
    minHeight: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    icon: path.join(__dirname, 'assets', 'icon.png'),
  });

  mainWindow.loadURL('http://localhost:8001');

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Create context menu
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {
      label: 'File',
      submenu: [
        { role: 'exit' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
      ],
    },
  ]));
}

async function startBackend() {
  console.log('[*] Starting backend...');
  const backendDir = path.join(__dirname, '..', 'backend');
  const pythonExe = path.join(backendDir, '.venv', 'Scripts', 'python.exe');

  if (!require('fs').existsSync(pythonExe)) {
    console.error('[!] Python venv not found. Run install.bat first.');
    return false;
  }

  backendProcess = spawn(pythonExe, [
    '-m', 'uvicorn', 'server_v2:app',
    '--host', '127.0.0.1',
    '--port', '8001',
  ], {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (data) => {
    console.log('[backend]', data.toString().trim());
  });

  backendProcess.stderr.on('data', (data) => {
    console.error('[backend err]', data.toString().trim());
  });

  backendProcess.on('error', (err) => {
    console.error('[backend error]', err);
  });

  console.log('[*] Waiting for backend to be ready...');
  const ready = await waitForBackend();
  if (!ready) {
    console.error('[!] Backend failed to start');
    return false;
  }

  console.log('[+] Backend ready!');
  return true;
}

async function startTor() {
  console.log('[*] Starting Tor...');
  const torPath = path.join(__dirname, '..', 'tor', 'tor.exe');
  const torrc = path.join(__dirname, '..', 'tor', 'torrc');

  if (!require('fs').existsSync(torPath)) {
    console.warn('[!] Tor binary not found. Skipping Tor (using fallback).');
    return false;
  }

  torProcess = spawn(torPath, ['-f', torrc], {
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  torProcess.on('error', (err) => {
    console.error('[tor error]', err);
  });

  await sleep(8000);
  console.log('[+] Tor started');
  return true;
}

app.on('ready', async () => {
  console.log('[*] App starting...');
  await startTor();
  const backendReady = await startBackend();

  if (!backendReady) {
    console.error('Failed to start backend');
    app.quit();
    return;
  }

  createWindow();
});

app.on('window-all-closed', () => {
  console.log('[*] Shutting down...');
  if (backendProcess) {
    backendProcess.kill();
  }
  if (torProcess) {
    torProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

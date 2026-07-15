# Windows Development / Standalone Setup

This app is **fully self-contained** — no cloud databases, no paid APIs, just local processes. Runs great on Windows 10/11 for personal use.

---

## 1. Prerequisites

| Tool | Version | Where |
|---|---|---|
| Python | 3.11+ | https://www.python.org/downloads/windows/ (tick "Add to PATH") |
| Node.js | 20+ | https://nodejs.org/ |
| Yarn | 1.22+ | `npm i -g yarn` |
| Git | Any | https://git-scm.com/download/win |
| Tor Expert Bundle | Latest | https://www.torproject.org/download/tor/ (**"Tor Expert Bundle"** — NOT the Browser) |

---

## 2. Install and configure Tor

1. Download **Tor Expert Bundle for Windows x86_64**.
2. Extract to `C:\tor\` — verify `C:\tor\tor\tor.exe` exists.
3. Create `C:\tor\torrc`:

```conf
SocksPort 9050
ControlPort 9051
CookieAuthentication 1
CookieAuthFileGroupReadable 1
DataDirectory C:\tor\data
Log notice file C:\tor\notice.log
ExitPolicy reject *:*
```

4. Start Tor (keep this PowerShell window open, or install as a service — see below):

```powershell
C:\tor\tor\tor.exe -f C:\tor\torrc
```

5. Verify (in another shell):

```powershell
curl.exe --socks5-hostname 127.0.0.1:9050 https://api.ipify.org
```

You should see a Tor exit IP.

### Optional: install Tor as a Windows service (survives reboots)

```powershell
# 1) Install NSSM: https://nssm.cc/download
nssm install tor "C:\tor\tor\tor.exe" -f C:\tor\torrc
nssm start tor
```

---

## 3. Backend

```powershell
cd C:\path\to\socialmediabooster\backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install stem aiosqlite pysocks "requests[socks]" playwright

playwright install chromium
```

Create `backend\.env`:

```
CORS_ORIGINS=*
BROWSER_MODE=playwright
TOR_SOCKS=socks5://127.0.0.1:9050
TOR_CONTROL_PORT=9051
ROTATION_INTERVAL=3
LOG_RETENTION_DAYS=7
SQLITE_PATH=.\data\yt_booster.db
```

Run:

```powershell
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Verify:

```powershell
curl.exe http://localhost:8001/api/health
```

Expected: `{"api":"ok","db":"ok","storage":"sqlite"}`

The SQLite database file is created automatically at `backend\data\yt_booster.db` on first run.

---

## 4. Frontend

```powershell
cd C:\path\to\socialmediabooster\frontend
yarn install
```

Create `frontend\.env`:

```
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=3000
```

Run:

```powershell
yarn start
```

Open http://localhost:3000

---

## 5. Watch-duration presets

The UI lets you pick one of five presets — for **non-custom** presets, every video watches a **random duration inside the selected range**, which looks more organic than a fixed number:

| Preset | Range (seconds) |
|---|---|
| Short   | 30 – 60 |
| Medium  | 90 – 180 |
| Long    | 240 – 420 |
| X-Long  | 460 – 800 |
| Custom  | fixed value from the "Watch (custom)" input |

Every 3 videos processed, the engine also rotates the Tor exit (and, if you chose "Specific list", picks a different country from your list).

---

## 6. Common gotchas

| Problem | Fix |
|---|---|
| `stem.SocketError: [WinError 10061]` | Tor isn't listening on 9051. Start `tor.exe` first. |
| `playwright: command not found` | Reactivate the venv: `.\.venv\Scripts\Activate.ps1` |
| Playwright launches then closes instantly | Windows Defender may be blocking `chrome-headless-shell.exe` — add an exception. |
| Tor closes when PowerShell closes | Install as service via NSSM (see step 2). |
| `db=error` on `/api/health` | Ensure the `SQLITE_PATH` directory exists (backend creates it, but if you set an unusual path make sure it's writable). |
| Very slow first Tor request | Tor is bootstrapping (60–90 s the first time). Give it a minute. |

---

## 7. File layout

```
socialmediabooster/
├── backend/
│   ├── server.py               # FastAPI + Tor rotation orchestration
│   ├── local_storage.py        # aiosqlite adapter (drop-in for the ex-Supabase client)
│   ├── browser_runner.py       # Playwright Chromium via SOCKS5
│   ├── requirements.txt
│   ├── .env
│   └── data/yt_booster.db      # ← your local database (auto-created)
├── frontend/
│   ├── src/App.js
│   ├── package.json
│   └── .env
├── WINDOWS_SETUP.md            # this file
└── README.md
```

No `.git` credentials, no cloud creds — you can zip this folder and run it on any Windows PC with the same prereqs.

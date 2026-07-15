# Windows Development Setup

This guide sets up the YT Views Booster stack (backend + frontend + Tor + Playwright) on **Windows 10/11 for local development**. The production deployment continues to run on the Linux container.

---

## 1. Prerequisites

| Tool | Version | Install command |
|---|---|---|
| Python | 3.11+ | https://www.python.org/downloads/windows/ (check "Add to PATH") |
| Node.js | 20+ | https://nodejs.org/ |
| Yarn | 1.22+ | `npm i -g yarn` |
| Git | Any | https://git-scm.com/download/win |
| Tor Expert Bundle | Latest | https://www.torproject.org/download/tor/ (**"Tor Expert Bundle"**, not the Browser) |

---

## 2. Install and configure Tor on Windows

1. Download the **Tor Expert Bundle for Windows x86_64**.
2. Extract to `C:\tor\` — you should have `C:\tor\tor\tor.exe`.
3. Create `C:\tor\torrc` with the following content:

```conf
SocksPort 9050
ControlPort 9051
CookieAuthentication 1
CookieAuthFileGroupReadable 1
DataDirectory C:\tor\data
Log notice file C:\tor\notice.log
ExitPolicy reject *:*
```

4. Start Tor as a background process (run in an admin PowerShell that stays open, or install it as a service):

```powershell
C:\tor\tor\tor.exe -f C:\tor\torrc
```

5. Verify Tor is running:

```powershell
curl.exe --socks5-hostname 127.0.0.1:9050 https://api.ipify.org
```

You should see a Tor exit IP.

> **Optional (run Tor as a Windows service):** Use [NSSM](https://nssm.cc/) — `nssm install tor "C:\tor\tor\tor.exe" -f C:\tor\torrc`.

### Cookie auth path on Windows

The Python `stem` library expects the control cookie to be readable. On Windows it will be at `C:\tor\data\control_auth_cookie`. The backend `Controller.from_port` code path used here works cross-platform.

---

## 3. Backend

```powershell
cd C:\path\to\socialmediabooster\backend

# Create a virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Dependencies
pip install -r requirements.txt
pip install stem httpx pysocks "requests[socks]" playwright

# Playwright browsers
playwright install chromium
```

Create `backend\.env`:

```
CORS_ORIGINS=*
SUPABASE_URL=https://supabase.dalvi.cloud
SUPABASE_SERVICE_KEY=<your service_role key>
BROWSER_MODE=playwright
TOR_SOCKS=socks5://127.0.0.1:9050
TOR_CONTROL_PORT=9051
ROTATION_INTERVAL=3
LOG_RETENTION_DAYS=7
# The Mongo variables are unused on Windows but kept for parity
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
```

Run the backend:

```powershell
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Verify:

```powershell
curl.exe http://localhost:8001/api/health
```

Expected: `{"api":"ok","supabase":"ok"}`

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

## 5. Common Windows gotchas

| Problem | Fix |
|---|---|
| `stem.SocketError: [WinError 10061]` | Tor isn't listening on 9051. Start `tor.exe` first. |
| `playwright: command not found` | Reactivate the venv: `.\.venv\Scripts\Activate.ps1` |
| Browser launches then closes instantly | Run `playwright install-deps` (Linux only) or make sure Windows Defender isn't blocking `chrome.exe`. |
| Tor keeps closing when PowerShell closes | Install as service via NSSM (see step 2). |
| PostgREST 400 from Supabase | Ensure `SUPABASE_SERVICE_KEY` is the *service_role* key, not anon. |

---

## 6. Directory summary

```
socialmediabooster/
├── backend/                # FastAPI + Tor rotation + Playwright
│   ├── server.py
│   ├── supabase_client.py
│   ├── browser_runner.py
│   ├── requirements.txt
│   └── .env
├── frontend/               # React SPA
│   ├── src/App.js
│   ├── package.json
│   └── .env
├── supabase_schema.sql     # One-time DDL (auto-applied by backend on startup)
├── WINDOWS_SETUP.md        # this file
└── README.md
```

The backend automatically applies `supabase_schema.sql` at startup via Supabase pg-meta, so you don't need to run it manually. If you prefer to run it yourself, paste it into the Supabase Studio SQL editor.

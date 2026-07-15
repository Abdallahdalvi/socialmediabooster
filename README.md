# SocialMediaBooster — YT Views + Tor IP Rotation (self-contained)

Educational/research tool that simulates distributed YouTube traffic and rotates a fresh **Tor exit IP + country every 3 videos**. **Zero cloud dependencies** — SQLite on disk, Tor's built-in GeoIP database for country lookups, and headless Chromium (Playwright) routed through Tor SOCKS5.

> ⚠️ **For testing and educational purposes only.** Automated view inflation violates YouTube's ToS.

## What's inside

| Component | Local? | Notes |
|---|---|---|
| React frontend | ✅ | Vite/CRA on port 3000 |
| FastAPI backend | ✅ | Port 8001 |
| SQLite database | ✅ | Single file at `backend/data/yt_booster.db` |
| Tor daemon | ✅ | SocksPort 9050, ControlPort 9051 (cookie auth) |
| Playwright Chromium | ✅ | Real headless browser, SOCKS5 → Tor |
| IP geolocation | ✅ | Tor's bundled GeoIP db (via ControlPort) — **no external API** |
| Exit-IP verification | Public IP lookup (api.ipify.org / icanhazip.com fallbacks) via Tor |

## Highlights

- **IP rotation every 3 videos** — `SIGNAL NEWNYM` + optional `ExitNodes` country pinning.
- **Watch duration presets** — pick one, each video watches a *random* duration in the range:
  - `short` — 30–60 s
  - `medium` — 90–180 s
  - `long` — 240–420 s
  - `xlong` — 460–800 s
  - `custom` — fixed value from the input
- **3 location strategies:** Random worldwide, Specific country list, Auto-match audience.
- **Two engines:** Playwright (real Chromium + mouse simulation) or fast HTTP fallback.
- **Persistent SSE log stream** — logs stored in SQLite, replayed on reload, auto-purged after 7 days.
- **Force-Rotate-Now** manual control.
- **Runs offline-ish** — after `pip install` + `playwright install chromium`, no cloud services or paid APIs.

## Quick start — Linux (container / server)

Backend, frontend, and Tor are managed by supervisor. Just:

```bash
sudo supervisorctl restart backend frontend tor
```

Open the frontend at `REACT_APP_BACKEND_URL` (see `frontend/.env`).

## Quick start — Windows PC

See [`WINDOWS_SETUP.md`](./WINDOWS_SETUP.md). One-time steps:

1. Install Python 3.11, Node 20, Yarn, Tor Expert Bundle.
2. `python -m venv .venv && .venv\Scripts\Activate.ps1`
3. `pip install -r backend\requirements.txt`
4. `pip install stem aiosqlite pysocks "requests[socks]" playwright`
5. `playwright install chromium`
6. Start Tor: `C:\tor\tor\tor.exe -f C:\tor\torrc`
7. Start backend: `uvicorn server:app --port 8001 --reload`
8. In another shell: `cd frontend && yarn && yarn start`

That's it — no Docker, no cloud DB, no API keys.

## Environment (`backend/.env`)

```
CORS_ORIGINS=*
BROWSER_MODE=playwright        # or 'http'
TOR_SOCKS=socks5://127.0.0.1:9050
TOR_CONTROL_PORT=9051
ROTATION_INTERVAL=3
LOG_RETENTION_DAYS=7
SQLITE_PATH=./data/yt_booster.db
```

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/` | Version + config + duration presets |
| `GET` | `/api/health` | DB reachability |
| `GET` | `/api/tor/status` | Current exit IP + country |
| `POST` | `/api/tor/rotate` | Force new circuit (optional `countries` body) |
| `POST` | `/api/jobs` | Enqueue a job (accepts `duration_preset`) |
| `GET` | `/api/jobs` | List (newest first) |
| `GET` | `/api/jobs/{id}` | Full job doc |
| `GET` | `/api/jobs/{id}/logs` | Persisted log lines |
| `GET` | `/api/jobs/{id}/stream` | SSE — replays history then streams live |
| `GET` | `/api/stats` | Aggregate metrics |
| `GET` | `/api/countries` | Supported exit countries |

## Data model

Auto-created on first backend startup — no manual SQL needed.

- `yt_jobs (id TEXT PK, video_urls JSON, duration_preset, ...)`
- `yt_job_logs (id INTEGER PK, job_id TEXT FK, level, msg, ip, country, ts)`

## License

MIT. Use responsibly.

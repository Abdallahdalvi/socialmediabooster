# SocialMediaBooster — YT Views + Tor IP Rotation

Educational/research tool that simulates distributed YouTube traffic and rotates a fresh **Tor exit IP + country every 3 videos** to avoid single-IP fingerprinting. Real headless Chromium (Playwright) routed through Tor SOCKS5.

> ⚠️ **For testing and educational purposes only.** Automated view inflation violates YouTube's ToS.

## Stack

- **Backend:** FastAPI + Playwright + Tor (via `stem`) + Supabase (PostgREST)
- **Frontend:** React 19 + Tailwind + framer-motion (retro-terminal aesthetic)
- **Storage:** Supabase Postgres (`yt_jobs`, `yt_job_logs`) — schema auto-applied on startup
- **Traffic:** every 3 videos → `SIGNAL NEWNYM` on the Tor ControlPort + optional `ExitNodes` country pinning

## Highlights

- **IP rotation every 3 videos** — verified live (US → DE → GB in one job)
- **3 location strategies:** Random worldwide, Specific country list, Auto-match audience
- **Real Chromium playback** via SOCKS5 to Tor — mouse movement, muted audio, randomized viewport/UA/timezone/locale
- **Fast HTTP fallback** engine when you don't need a full browser
- **Persistent SSE log stream** — logs stored in Supabase, replayed on reload, auto-purged after 7 days
- **Force-Rotate-Now** manual control

## Quick start (Linux container / production)

Backend, frontend, Tor, and MongoDB are managed by supervisor. Just:

```bash
sudo supervisorctl restart backend frontend
```

Then open the frontend at `REACT_APP_BACKEND_URL`.

## Quick start (Windows dev)

See [`WINDOWS_SETUP.md`](./WINDOWS_SETUP.md).

## Environment

`backend/.env`:

```
CORS_ORIGINS=*
SUPABASE_URL=https://supabase.dalvi.cloud
SUPABASE_SERVICE_KEY=<service_role key>
BROWSER_MODE=playwright        # or 'http'
TOR_SOCKS=socks5://127.0.0.1:9050
TOR_CONTROL_PORT=9051
ROTATION_INTERVAL=3
LOG_RETENTION_DAYS=7
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
```

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/` | Version + config |
| `GET` | `/api/health` | Supabase reachability |
| `GET` | `/api/tor/status` | Current exit IP + country |
| `POST` | `/api/tor/rotate` | Force new circuit (optional `countries` body) |
| `POST` | `/api/jobs` | Enqueue a job |
| `GET` | `/api/jobs` | List (newest first) |
| `GET` | `/api/jobs/{id}` | Full job doc |
| `GET` | `/api/jobs/{id}/logs` | Persisted log lines |
| `GET` | `/api/jobs/{id}/stream` | SSE — replays history then streams live |
| `GET` | `/api/stats` | Aggregate metrics |
| `GET` | `/api/countries` | Supported exit countries |

## Data model

Auto-created in Supabase via `supabase_schema.sql` on backend startup.

- `yt_jobs (id uuid pk, video_urls jsonb, ...)` — one row per job
- `yt_job_logs (id bigserial pk, job_id uuid fk, level, msg, ip, country, ts)` — one row per event

## License

MIT. Use responsibly.

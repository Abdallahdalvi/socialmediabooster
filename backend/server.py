from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import asyncio
import json
import uuid
import re
import random
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timezone, timedelta

import requests
from stem import Signal
from stem.control import Controller

from local_storage import get_store
from browser_runner import visit_via_playwright

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = FastAPI(title="YT Views Booster")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOR_SOCKS_HTTP = "socks5h://127.0.0.1:9050"
TOR_SOCKS_BROWSER = os.environ.get("TOR_SOCKS", "socks5://127.0.0.1:9050")
TOR_CONTROL_PORT = int(os.environ.get("TOR_CONTROL_PORT", "9051"))
ROTATION_INTERVAL = int(os.environ.get("ROTATION_INTERVAL", "3"))
BROWSER_MODE = os.environ.get("BROWSER_MODE", "playwright")  # 'playwright' | 'http'
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "7"))

db = get_store()

# ---------------- Duration presets ----------------

DURATION_PRESETS: Dict[str, Tuple[int, int]] = {
    "short":  (30, 60),
    "medium": (90, 180),
    "long":   (240, 420),
    "xlong":  (460, 800),
}

def resolve_watch_seconds(preset: str, fallback: int) -> int:
    rng = DURATION_PRESETS.get(preset)
    if not rng:
        return max(3, min(1200, fallback))
    return random.randint(rng[0], rng[1])

# ---------------- Models ----------------

class JobCreate(BaseModel):
    video_urls: List[str]
    views_per_video: int = 3
    watch_seconds: int = 8               # used only when duration_preset == 'custom'
    duration_preset: str = "custom"      # 'short'|'medium'|'long'|'xlong'|'custom'
    location_mode: str = "random"        # 'random' | 'specific' | 'auto'
    countries: List[str] = []
    browser_mode: Optional[str] = None   # 'playwright' | 'http'

class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    video_urls: List[str]
    views_per_video: int
    watch_seconds: int
    duration_preset: str = "custom"
    location_mode: str
    countries: List[str] = []
    status: str = "queued"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    total_videos: int = 0
    processed_videos: int = 0
    total_views_delivered: int = 0
    unique_ips: List[str] = []
    countries_covered: List[str] = []
    failures: int = 0
    current_ip: Optional[str] = None
    current_country: Optional[str] = None
    current_country_code: Optional[str] = None

# ---------------- Broadcaster (in-memory + local DB persistence) ----------------

class Broadcaster:
    def __init__(self):
        self.queues: Dict[str, List[asyncio.Queue]] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.queues.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue):
        if job_id in self.queues and q in self.queues[job_id]:
            self.queues[job_id].remove(q)

    async def publish(self, job_id: str, event: dict):
        event = {**event, "ts": datetime.now(timezone.utc).isoformat()}
        # push to live subscribers
        for q in self.queues.get(job_id, []):
            try:
                q.put_nowait(event)
            except Exception:
                pass
        # persist to local DB (best-effort)
        row = {
            "job_id": job_id,
            "level": event.get("level", "info"),
            "msg": event.get("msg", ""),
            "ip": event.get("ip"),
            "country": event.get("country"),
            "country_code": event.get("country_code"),
            "ts": event["ts"],
        }
        try:
            asyncio.create_task(db.insert("yt_job_logs", row))
        except Exception as e:
            logger.warning(f"log persist failed: {e}")

broadcaster = Broadcaster()

# ---------------- Tor helpers (no external deps needed) ----------------

def tor_get_exit_ip() -> Optional[str]:
    """Fetch our current Tor exit IP. Tries multiple minimal services;
    each returns just an IP string so this doesn't leak PII."""
    endpoints = [
        "https://api.ipify.org?format=json",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, proxies={"http": TOR_SOCKS_HTTP, "https": TOR_SOCKS_HTTP}, timeout=15)
            if r.status_code != 200:
                continue
            text = r.text.strip()
            try:
                data = json.loads(text)
                ip = data.get("ip")
            except Exception:
                ip = text.split()[0] if text else None
            if ip and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                return ip
        except Exception:
            continue
    return None

def tor_ip_geo(ip: str) -> Dict[str, str]:
    """Country/city lookup — uses Tor's built-in GeoIP database via the
    control port (offline, no third-party call). City/region left empty."""
    try:
        with Controller.from_port(port=TOR_CONTROL_PORT) as c:
            c.authenticate()
            cc = ""
            try:
                cc = (c.get_info(f"ip-to-country/{ip}") or "").upper()
            except Exception:
                cc = ""
            country_name = _CC_TO_NAME.get(cc, cc or "Unknown")
            return {"country": country_name, "country_code": cc, "city": "", "region": ""}
    except Exception:
        return {"country": "Unknown", "country_code": "", "city": "", "region": ""}

def tor_rotate_circuit(exit_countries: Optional[List[str]] = None) -> None:
    with Controller.from_port(port=TOR_CONTROL_PORT) as c:
        c.authenticate()
        if exit_countries:
            codes = ",".join([f"{{{cc.lower()}}}" for cc in exit_countries if cc])
            try:
                c.set_conf("ExitNodes", codes)
                c.set_conf("StrictNodes", "1")
            except Exception as e:
                logger.warning(f"set ExitNodes failed: {e}")
        else:
            try:
                c.reset_conf("ExitNodes")
                c.reset_conf("StrictNodes")
            except Exception:
                pass
        c.signal(Signal.NEWNYM)

def extract_video_id(url: str) -> Optional[str]:
    m = re.search(r"(?:v=|/shorts/|youtu\.be/|/embed/)([\w-]{11})", url)
    return m.group(1) if m else None

RANDOM_POOL = ["us", "gb", "de", "fr", "nl", "se", "ch", "ca", "in", "jp", "au", "br", "es", "it", "pl", "ro", "no"]

def pick_countries_for_batch(mode: str, user_list: List[str], batch_idx: int) -> List[str]:
    if mode == "specific" and user_list:
        return [user_list[batch_idx % len(user_list)].lower()]
    if mode == "auto":
        curated = ["us", "in", "gb", "de", "br", "id"]
        return [curated[batch_idx % len(curated)]]
    return [random.choice(RANDOM_POOL)]

# ---------------- HTTP fallback visit ----------------

async def visit_via_http(video_url: str, watch_seconds: int) -> bool:
    def _do():
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            r = requests.get(video_url, headers=headers,
                             proxies={"http": TOR_SOCKS_HTTP, "https": TOR_SOCKS_HTTP},
                             timeout=45)
            return r.status_code == 200 and len(r.text) > 1000
        except Exception:
            return False
    ok = await asyncio.to_thread(_do)
    await asyncio.sleep(min(watch_seconds, 60))
    return ok

# ---------------- Job runner ----------------

async def run_job(job_id: str, browser_mode: str):
    job_doc = await db.get_one("yt_jobs", {"id": job_id})
    if not job_doc:
        return

    urls = job_doc.get("video_urls", []) or []
    views_per_video = job_doc.get("views_per_video", 1)
    default_watch = job_doc.get("watch_seconds", 5)
    duration_preset = job_doc.get("duration_preset", "custom")
    location_mode = job_doc.get("location_mode", "random")
    countries_cfg = job_doc.get("countries", []) or []

    # Expand queue
    queue: List[str] = []
    for u in urls:
        queue.extend([u] * views_per_video)
    total = len(queue)
    await db.update("yt_jobs", {"id": job_id}, {"status": "running", "total_videos": total})

    preset_hint = (
        f"{DURATION_PRESETS[duration_preset][0]}–{DURATION_PRESETS[duration_preset][1]}s (random per video)"
        if duration_preset in DURATION_PRESETS
        else f"{default_watch}s fixed"
    )
    await broadcaster.publish(job_id, {"level": "info",
        "msg": f"Job started. total_videos={total}, rotate_every={ROTATION_INTERVAL}, "
               f"engine={browser_mode}, watch={preset_hint}"})

    unique_ips = set()
    countries_covered = set()
    processed = 0
    delivered = 0
    failures = 0
    batch_idx = 0
    ip = None
    geo = {"country": "?", "country_code": ""}

    async def rotate_and_probe(picked_countries: List[str], announce_prefix: str = ""):
        nonlocal ip, geo
        await broadcaster.publish(job_id, {"level": "tor",
            "msg": f"{announce_prefix}rotating Tor circuit → exit country: {picked_countries}"})
        try:
            await asyncio.to_thread(tor_rotate_circuit, picked_countries)
        except Exception as e:
            await broadcaster.publish(job_id, {"level": "warn", "msg": f"circuit rotate failed: {e}"})
        await asyncio.sleep(6)
        ip = await asyncio.to_thread(tor_get_exit_ip)
        if ip:
            geo = await asyncio.to_thread(tor_ip_geo, ip)
            unique_ips.add(ip)
            countries_covered.add(geo["country_code"] or geo["country"])
        await broadcaster.publish(job_id, {
            "level": "ip",
            "msg": f"Active exit IP: {ip} ({geo.get('country','?')})",
            "ip": ip, "country": geo.get("country"), "country_code": geo.get("country_code"),
        })

    picked = pick_countries_for_batch(location_mode, countries_cfg, batch_idx)
    await rotate_and_probe(picked)

    for i, url in enumerate(queue, start=1):
        if i > 1 and (i - 1) % ROTATION_INTERVAL == 0:
            batch_idx += 1
            picked = pick_countries_for_batch(location_mode, countries_cfg, batch_idx)
            await rotate_and_probe(picked, announce_prefix=f"[rotation @ video #{i}] ")

        vid = extract_video_id(url) or url
        next_rot = ROTATION_INTERVAL - ((i - 1) % ROTATION_INTERVAL) - 1
        this_watch = resolve_watch_seconds(duration_preset, default_watch)
        engine = "playwright" if browser_mode == "playwright" else "http"
        await broadcaster.publish(job_id, {"level": "play",
            "msg": f"[{i}/{total}] [{engine}] visiting {vid} via {ip} for {this_watch}s  |  next rotation in {next_rot} video(s)"})

        try:
            if browser_mode == "playwright":
                ok = await visit_via_playwright(url, this_watch, socks=TOR_SOCKS_BROWSER)
            else:
                ok = await visit_via_http(url, this_watch)
        except Exception as e:
            await broadcaster.publish(job_id, {"level": "error", "msg": f"visit error: {e}"})
            ok = False

        processed += 1
        if ok:
            delivered += 1
            await broadcaster.publish(job_id, {"level": "ok",
                "msg": f"[{i}/{total}] view delivered ✓ ({this_watch}s watched, total: {delivered})"})
        else:
            failures += 1
            await broadcaster.publish(job_id, {"level": "error",
                "msg": f"[{i}/{total}] view failed ✗"})

        await db.update("yt_jobs", {"id": job_id}, {
            "processed_videos": processed,
            "total_views_delivered": delivered,
            "unique_ips": list(unique_ips),
            "countries_covered": list(countries_covered),
            "failures": failures,
            "current_ip": ip,
            "current_country": geo.get("country"),
            "current_country_code": geo.get("country_code"),
        })

    await db.update("yt_jobs", {"id": job_id}, {
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    await broadcaster.publish(job_id, {"level": "done",
        "msg": f"Job completed. delivered={delivered}/{total}, unique IPs={len(unique_ips)}, countries={len(countries_covered)}"})

# ---------------- Log retention ----------------

async def log_retention_loop():
    while True:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)).isoformat()
            await db.raw_delete("yt_job_logs", f"ts=lt.{cutoff}")
            logger.info(f"purged logs older than {cutoff}")
        except Exception as e:
            logger.warning(f"log purge failed: {e}")
        await asyncio.sleep(6 * 3600)

# ---------------- API endpoints ----------------

@api_router.get("/")
async def root():
    return {
        "message": "YT Views Booster API",
        "rotation_interval": ROTATION_INTERVAL,
        "browser_mode": BROWSER_MODE,
        "storage": "sqlite",
        "duration_presets": {k: list(v) for k, v in DURATION_PRESETS.items()},
    }

@api_router.get("/health")
async def health():
    ok = await db.health()
    return {"api": "ok", "db": "ok" if ok else "error", "storage": "sqlite"}

@api_router.get("/tor/status")
async def tor_status():
    ip = await asyncio.to_thread(tor_get_exit_ip)
    if not ip:
        return {"ok": False, "ip": None, "country": None}
    geo = await asyncio.to_thread(tor_ip_geo, ip)
    return {"ok": True, "ip": ip, **geo}

@api_router.post("/tor/rotate")
async def tor_rotate(payload: dict = None):
    countries = (payload or {}).get("countries") or None
    await asyncio.to_thread(tor_rotate_circuit, countries)
    await asyncio.sleep(6)
    ip = await asyncio.to_thread(tor_get_exit_ip)
    geo = await asyncio.to_thread(tor_ip_geo, ip) if ip else {}
    return {"ok": True, "ip": ip, **geo}

@api_router.post("/jobs", response_model=Job)
async def create_job(payload: JobCreate):
    urls = [u.strip() for u in (payload.video_urls or []) if u.strip()]
    if not urls:
        raise HTTPException(400, "video_urls required")
    if payload.duration_preset not in ("custom", *DURATION_PRESETS.keys()):
        raise HTTPException(400, f"invalid duration_preset (allowed: custom, {', '.join(DURATION_PRESETS)})")
    job = Job(
        video_urls=urls,
        views_per_video=max(1, min(50, payload.views_per_video)),
        watch_seconds=max(3, min(1200, payload.watch_seconds)),
        duration_preset=payload.duration_preset,
        location_mode=payload.location_mode,
        countries=[c.strip().lower() for c in (payload.countries or []) if c.strip()],
    )
    await db.insert("yt_jobs", job.model_dump())
    bm = (payload.browser_mode or BROWSER_MODE).lower()
    if bm not in ("playwright", "http"):
        bm = BROWSER_MODE
    asyncio.create_task(run_job(job.id, bm))
    return job

@api_router.get("/jobs", response_model=List[Job])
async def list_jobs():
    rows = await db.select("yt_jobs", order="created_at.desc", limit=200)
    return [Job(**r) for r in rows]

@api_router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    row = await db.get_one("yt_jobs", {"id": job_id})
    if not row:
        raise HTTPException(404, "Job not found")
    return row

@api_router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, limit: int = 500):
    rows = await db.select("yt_job_logs", match={"job_id": job_id}, order="ts.asc", limit=limit)
    return {"job_id": job_id, "logs": rows}

@api_router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_gen():
        q = broadcaster.subscribe(job_id)
        try:
            # replay persisted history first
            try:
                history = await db.select("yt_job_logs", match={"job_id": job_id},
                                          order="ts.asc", limit=500)
                for h in history:
                    yield f"data: {json.dumps(h)}\n\n"
            except Exception:
                pass
            yield f"data: {json.dumps({'level':'sys','msg':'connected'})}\n\n"
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(job_id, q)
    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@api_router.get("/stats")
async def stats():
    rows = await db.select("yt_jobs", columns="total_views_delivered,unique_ips,countries_covered")
    total_views = sum(r.get("total_views_delivered", 0) for r in rows)
    unique_ips = set()
    countries = set()
    for r in rows:
        unique_ips.update(r.get("unique_ips", []) or [])
        countries.update(r.get("countries_covered", []) or [])
    return {
        "total_jobs": len(rows),
        "total_views_delivered": total_views,
        "unique_ips": len(unique_ips),
        "countries": len(countries),
    }

@api_router.get("/countries")
async def countries():
    return {"list": [{"code": k, "name": v} for k, v in _CC_TO_NAME.items() if k in [c.upper() for c in RANDOM_POOL] + ["ID"]]}

# ---------------- ISO 3166-1 alpha-2 → country name (minimal offline map) ----------------
_CC_TO_NAME: Dict[str, str] = {
    "US": "United States", "GB": "United Kingdom", "DE": "Germany", "FR": "France",
    "NL": "Netherlands", "SE": "Sweden", "CH": "Switzerland", "CA": "Canada",
    "IN": "India", "JP": "Japan", "AU": "Australia", "BR": "Brazil",
    "ES": "Spain", "IT": "Italy", "PL": "Poland", "RO": "Romania",
    "NO": "Norway", "ID": "Indonesia", "AT": "Austria", "BE": "Belgium",
    "CZ": "Czechia", "DK": "Denmark", "FI": "Finland", "IE": "Ireland",
    "LU": "Luxembourg", "PT": "Portugal", "RU": "Russia", "SG": "Singapore",
    "UA": "Ukraine", "TR": "Türkiye", "MX": "Mexico", "AR": "Argentina",
    "ZA": "South Africa", "KR": "South Korea", "HK": "Hong Kong", "TW": "Taiwan",
    "BG": "Bulgaria", "HU": "Hungary", "IS": "Iceland", "IL": "Israel",
    "MY": "Malaysia", "NZ": "New Zealand", "PH": "Philippines", "TH": "Thailand",
    "VN": "Vietnam", "GR": "Greece", "LV": "Latvia", "LT": "Lithuania",
    "SK": "Slovakia", "SI": "Slovenia", "EE": "Estonia", "MD": "Moldova",
    "MK": "North Macedonia", "RS": "Serbia", "HR": "Croatia", "AL": "Albania",
    "BY": "Belarus", "CL": "Chile", "CO": "Colombia", "PE": "Peru",
    "VE": "Venezuela", "UY": "Uruguay", "IR": "Iran", "IQ": "Iraq",
    "SA": "Saudi Arabia", "AE": "United Arab Emirates", "EG": "Egypt", "KE": "Kenya",
    "NG": "Nigeria", "MA": "Morocco", "TN": "Tunisia", "PK": "Pakistan",
    "BD": "Bangladesh", "LK": "Sri Lanka", "NP": "Nepal", "KZ": "Kazakhstan",
}

app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Serve the built React app in "standalone" mode ----
# When packaged as a single executable (PyInstaller) or run via start.bat,
# the frontend is a static build sitting next to server.py.
_FRONTEND_CANDIDATES = [
    ROOT_DIR / "static",                   # copied build (used by PyInstaller)
    ROOT_DIR.parent / "frontend" / "build" # dev / launcher.bat convention
]
_FRONTEND_ROOT = next((p for p in _FRONTEND_CANDIDATES if (p / "index.html").exists()), None)

if _FRONTEND_ROOT is not None:
    logger.info(f"Serving static frontend from {_FRONTEND_ROOT}")

    # Mount hashed asset dir first so /static/* CSS + JS resolve
    _ASSETS = _FRONTEND_ROOT / "static"
    if _ASSETS.exists():
        app.mount("/static", StaticFiles(directory=str(_ASSETS)), name="frontend-static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # never intercept the API
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = _FRONTEND_ROOT / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_ROOT / "index.html"))
else:
    logger.info("No frontend build found — API only mode.")

@app.on_event("startup")
async def _startup():
    try:
        await db.init_schema()
        logger.info(f"SQLite schema initialised at {db.db_path}")
    except Exception as e:
        logger.error(f"schema init failed: {e}")
    asyncio.create_task(log_retention_loop())

@app.on_event("shutdown")
async def _shutdown():
    await db.close()

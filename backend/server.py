from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta

import requests
from stem import Signal
from stem.control import Controller

from supabase_client import get_supabase
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

sb = get_supabase()

# ---------------- Models ----------------

class JobCreate(BaseModel):
    video_urls: List[str]
    views_per_video: int = 3
    watch_seconds: int = 8
    location_mode: str = "random"  # random | specific | auto
    countries: List[str] = []
    browser_mode: Optional[str] = None  # override server default: 'playwright' or 'http'

class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    video_urls: List[str]
    views_per_video: int
    watch_seconds: int
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

# ---------------- Broadcaster (in-memory + Supabase persistence) ----------------

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
        # persist to Supabase (non-blocking)
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
            asyncio.create_task(sb.insert("yt_job_logs", row))
        except Exception as e:
            logger.warning(f"log persist failed: {e}")

broadcaster = Broadcaster()

# ---------------- Tor helpers ----------------

def tor_get_exit_ip() -> Optional[str]:
    try:
        r = requests.get("https://api.ipify.org?format=json",
                         proxies={"http": TOR_SOCKS_HTTP, "https": TOR_SOCKS_HTTP}, timeout=25)
        return r.json().get("ip")
    except Exception as e:
        logger.warning(f"exit ip fetch failed: {e}")
        return None

def tor_ip_geo(ip: str) -> Dict[str, str]:
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}",
                         params={"fields": "status,country,countryCode,region,city"}, timeout=10)
        d = r.json()
        if d.get("status") == "success":
            return {
                "country": d.get("country") or "Unknown",
                "country_code": (d.get("countryCode") or "").upper(),
                "city": d.get("city") or "",
                "region": d.get("region") or "",
            }
    except Exception:
        pass
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
    await asyncio.sleep(min(watch_seconds, 15))
    return ok

# ---------------- Job runner ----------------

async def run_job(job_id: str, browser_mode: str):
    job_doc = await sb.get_one("yt_jobs", {"id": job_id})
    if not job_doc:
        return

    urls = job_doc.get("video_urls", []) or []
    views_per_video = job_doc.get("views_per_video", 1)
    watch_seconds = job_doc.get("watch_seconds", 5)
    location_mode = job_doc.get("location_mode", "random")
    countries_cfg = job_doc.get("countries", []) or []

    # Expand queue
    queue: List[str] = []
    for u in urls:
        queue.extend([u] * views_per_video)
    total = len(queue)
    await sb.update("yt_jobs", {"id": job_id}, {"status": "running", "total_videos": total})
    await broadcaster.publish(job_id, {"level": "info",
        "msg": f"Job started. total_videos={total}, rotate_every={ROTATION_INTERVAL}, browser_mode={browser_mode}"})

    unique_ips = set()
    countries_covered = set()
    processed = 0
    delivered = 0
    failures = 0
    batch_idx = 0
    ip = None
    geo = {"country": "?", "country_code": ""}

    # First circuit
    picked = pick_countries_for_batch(location_mode, countries_cfg, batch_idx)
    await broadcaster.publish(job_id, {"level": "tor", "msg": f"rotating Tor circuit → exit country: {picked}"})
    try:
        await asyncio.to_thread(tor_rotate_circuit, picked)
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
        "msg": f"Active exit IP: {ip} ({geo.get('country','?')} {geo.get('city','')})",
        "ip": ip, "country": geo.get("country"), "country_code": geo.get("country_code"),
    })

    for i, url in enumerate(queue, start=1):
        if i > 1 and (i - 1) % ROTATION_INTERVAL == 0:
            batch_idx += 1
            picked = pick_countries_for_batch(location_mode, countries_cfg, batch_idx)
            await broadcaster.publish(job_id, {"level": "tor",
                "msg": f"[rotation] video #{i} → new circuit, exit: {picked}"})
            try:
                await asyncio.to_thread(tor_rotate_circuit, picked)
            except Exception as e:
                await broadcaster.publish(job_id, {"level": "warn", "msg": f"rotate error: {e}"})
            await asyncio.sleep(6)
            ip = await asyncio.to_thread(tor_get_exit_ip)
            if ip:
                geo = await asyncio.to_thread(tor_ip_geo, ip)
                unique_ips.add(ip)
                countries_covered.add(geo["country_code"] or geo["country"])
            await broadcaster.publish(job_id, {
                "level": "ip",
                "msg": f"Active exit IP: {ip} ({geo.get('country','?')} {geo.get('city','')})",
                "ip": ip, "country": geo.get("country"), "country_code": geo.get("country_code"),
            })

        vid = extract_video_id(url) or url
        next_rot = ROTATION_INTERVAL - ((i - 1) % ROTATION_INTERVAL) - 1
        engine = "playwright" if browser_mode == "playwright" else "http"
        await broadcaster.publish(job_id, {"level": "play",
            "msg": f"[{i}/{total}] [{engine}] visiting {vid} via {ip}  |  next rotation in {next_rot} video(s)"})

        try:
            if browser_mode == "playwright":
                ok = await visit_via_playwright(url, watch_seconds, socks=TOR_SOCKS_BROWSER)
            else:
                ok = await visit_via_http(url, watch_seconds)
        except Exception as e:
            await broadcaster.publish(job_id, {"level": "error", "msg": f"visit error: {e}"})
            ok = False

        processed += 1
        if ok:
            delivered += 1
            await broadcaster.publish(job_id, {"level": "ok",
                "msg": f"[{i}/{total}] view delivered ✓  (total delivered: {delivered})"})
        else:
            failures += 1
            await broadcaster.publish(job_id, {"level": "error",
                "msg": f"[{i}/{total}] view failed ✗"})

        await sb.update("yt_jobs", {"id": job_id}, {
            "processed_videos": processed,
            "total_views_delivered": delivered,
            "unique_ips": list(unique_ips),
            "countries_covered": list(countries_covered),
            "failures": failures,
            "current_ip": ip,
            "current_country": geo.get("country"),
            "current_country_code": geo.get("country_code"),
        })

    await sb.update("yt_jobs", {"id": job_id}, {
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
            await sb.raw_delete("yt_job_logs", f"ts=lt.{cutoff}")
            logger.info(f"purged logs older than {cutoff}")
        except Exception as e:
            logger.warning(f"log purge failed: {e}")
        await asyncio.sleep(6 * 3600)  # every 6h

# ---------------- API endpoints ----------------

@api_router.get("/")
async def root():
    return {
        "message": "YT Views Booster API",
        "rotation_interval": ROTATION_INTERVAL,
        "browser_mode": BROWSER_MODE,
        "storage": "supabase",
    }

@api_router.get("/health")
async def health():
    ok = await sb.health()
    return {"api": "ok", "supabase": "ok" if ok else "error"}

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
    job = Job(
        video_urls=urls,
        views_per_video=max(1, min(50, payload.views_per_video)),
        watch_seconds=max(3, min(60, payload.watch_seconds)),
        location_mode=payload.location_mode,
        countries=[c.strip().lower() for c in (payload.countries or []) if c.strip()],
    )
    row = job.model_dump()
    await sb.insert("yt_jobs", row)
    bm = (payload.browser_mode or BROWSER_MODE).lower()
    if bm not in ("playwright", "http"):
        bm = BROWSER_MODE
    asyncio.create_task(run_job(job.id, bm))
    return job

@api_router.get("/jobs", response_model=List[Job])
async def list_jobs():
    rows = await sb.select("yt_jobs", order="created_at.desc", limit=200)
    return [Job(**r) for r in rows]

@api_router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    row = await sb.get_one("yt_jobs", {"id": job_id})
    if not row:
        raise HTTPException(404, "Job not found")
    return row

@api_router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, limit: int = 500):
    rows = await sb.select("yt_job_logs", match={"job_id": job_id}, order="ts.asc", limit=limit)
    return {"job_id": job_id, "logs": rows}

@api_router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_gen():
        q = broadcaster.subscribe(job_id)
        try:
            # replay persisted history first
            try:
                history = await sb.select("yt_job_logs", match={"job_id": job_id},
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
    rows = await sb.select("yt_jobs", columns="total_views_delivered,unique_ips,countries_covered")
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
    return {
        "list": [
            {"code": "us", "name": "United States"},
            {"code": "gb", "name": "United Kingdom"},
            {"code": "de", "name": "Germany"},
            {"code": "fr", "name": "France"},
            {"code": "nl", "name": "Netherlands"},
            {"code": "se", "name": "Sweden"},
            {"code": "ch", "name": "Switzerland"},
            {"code": "ca", "name": "Canada"},
            {"code": "in", "name": "India"},
            {"code": "jp", "name": "Japan"},
            {"code": "au", "name": "Australia"},
            {"code": "br", "name": "Brazil"},
            {"code": "es", "name": "Spain"},
            {"code": "it", "name": "Italy"},
            {"code": "pl", "name": "Poland"},
            {"code": "ro", "name": "Romania"},
            {"code": "no", "name": "Norway"},
            {"code": "id", "name": "Indonesia"},
        ]
    }

app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _startup():
    # Auto-apply schema (idempotent) then reload PostgREST cache
    try:
        schema_path = ROOT_DIR.parent / "supabase_schema.sql"
        if schema_path.exists():
            sql = schema_path.read_text()
            await sb.execute_sql(sql)
            await sb.refresh_schema_cache()
            logger.info("supabase schema applied + cache reloaded")
    except Exception as e:
        logger.warning(f"schema apply failed (tables may already exist): {e}")
    # Fire-and-forget background purger
    asyncio.create_task(log_retention_loop())

@app.on_event("shutdown")
async def _shutdown():
    await sb.close()

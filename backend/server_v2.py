"""Updated FastAPI server with parallel job execution.

Key changes from server.py:
- Uses ParallelJobRunner for concurrent browser instances
- Supports configurable max_concurrent parameter per job
- Improved logging and stats tracking
- Better error handling
"""
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
from parallel_runner import ParallelJobRunner

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = FastAPI(title="YT Views Booster v2")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOR_SOCKS_HTTP = "socks5h://127.0.0.1:9050"
TOR_SOCKS_BROWSER = os.environ.get("TOR_SOCKS", "socks5://127.0.0.1:9050")
TOR_CONTROL_PORT = int(os.environ.get("TOR_CONTROL_PORT", "9051"))
ROTATION_INTERVAL = int(os.environ.get("ROTATION_INTERVAL", "3"))
BROWSER_MODE = os.environ.get("BROWSER_MODE", "playwright")
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "7"))
MAX_CONCURRENT_WORKERS = int(os.environ.get("MAX_CONCURRENT_WORKERS", "5"))

db = get_store()

# Duration presets
DURATION_PRESETS: Dict[str, Tuple[int, int]] = {
    "short": (30, 60),
    "medium": (90, 180),
    "long": (240, 420),
    "xlong": (460, 800),
}

# Broadcaster for SSE
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
        for q in self.queues.get(job_id, []):
            try:
                q.put_nowait(event)
            except Exception:
                pass

broadcaster = Broadcaster()

# Pydantic Models
class JobCreate(BaseModel):
    video_urls: List[str]
    views_per_video: int = 3
    watch_seconds: int = 8
    duration_preset: str = "custom"
    location_mode: str = "random"
    countries: List[str] = []
    browser_mode: Optional[str] = None
    max_concurrent: int = 5

class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    video_urls: List[str]
    views_per_video: int
    watch_seconds: int
    duration_preset: str = "custom"
    location_mode: str
    countries: List[str] = []
    browser_mode: str = "playwright"
    max_concurrent: int
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

# Tor Helpers
def tor_get_exit_ip() -> Optional[str]:
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

async def tor_rotate_async(exit_countries: Optional[List[str]] = None) -> Tuple[Optional[str], Optional[str]]:
    """Rotate Tor circuit and return (ip, country)."""
    await asyncio.to_thread(tor_rotate_circuit, exit_countries)
    await asyncio.sleep(6)
    ip = await asyncio.to_thread(tor_get_exit_ip)
    if ip:
        geo = await asyncio.to_thread(tor_ip_geo, ip)
        return ip, geo.get("country")
    return None, None

# API Endpoints
@api_router.get("/")
async def root():
    return {
        "message": "YT Views Booster API v2",
        "version": "2.0.0",
        "max_concurrent_workers": MAX_CONCURRENT_WORKERS,
        "rotation_interval": ROTATION_INTERVAL,
        "browser_mode": BROWSER_MODE,
        "duration_presets": {k: list(v) for k, v in DURATION_PRESETS.items()},
    }

@api_router.post("/jobs", response_model=Job)
async def create_job(payload: JobCreate):
    urls = [u.strip() for u in (payload.video_urls or []) if u.strip()]
    if not urls:
        raise HTTPException(400, "video_urls required")
    if payload.duration_preset not in ("custom", *DURATION_PRESETS.keys()):
        raise HTTPException(400, f"invalid duration_preset")

    job = Job(
        video_urls=urls,
        views_per_video=max(1, min(50, payload.views_per_video)),
        watch_seconds=max(3, min(1200, payload.watch_seconds)),
        duration_preset=payload.duration_preset,
        location_mode=payload.location_mode,
        countries=[c.strip().lower() for c in (payload.countries or []) if c.strip()],
        browser_mode=(payload.browser_mode or BROWSER_MODE).lower(),
        max_concurrent=max(1, min(20, payload.max_concurrent)),
    )

    await db.insert("yt_jobs", job.model_dump())

    # Start job asynchronously
    asyncio.create_task(run_parallel_job(
        job.id,
        job.video_urls,
        job.views_per_video,
        job.watch_seconds,
        job.duration_preset,
        job.location_mode,
        job.countries,
        job.browser_mode,
        job.max_concurrent,
    ))

    return job

async def run_parallel_job(
    job_id: str,
    video_urls: List[str],
    views_per_video: int,
    watch_seconds: int,
    duration_preset: str,
    location_mode: str,
    countries: List[str],
    browser_mode: str,
    max_concurrent: int,
):
    """Run job with parallel workers."""
    runner = ParallelJobRunner(
        job_id=job_id,
        video_urls=video_urls,
        views_per_video=views_per_video,
        watch_seconds=watch_seconds,
        duration_preset=duration_preset,
        location_mode=location_mode,
        countries=countries,
        browser_mode=browser_mode,
        max_concurrent=max_concurrent,
        rotation_interval=ROTATION_INTERVAL,
    )
    runner.broadcaster = broadcaster

    await runner.run(tor_rotator=tor_rotate_async)

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

@api_router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_gen():
        q = broadcaster.subscribe(job_id)
        try:
            try:
                history = await db.select("yt_job_logs", match={"job_id": job_id}, order="ts.asc", limit=500)
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
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

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

_CC_TO_NAME: Dict[str, str] = {
    "US": "United States", "GB": "United Kingdom", "DE": "Germany", "FR": "France",
    "NL": "Netherlands", "SE": "Sweden", "CH": "Switzerland", "CA": "Canada",
    "IN": "India", "JP": "Japan", "AU": "Australia", "BR": "Brazil",
    "ES": "Spain", "IT": "Italy", "PL": "Poland", "RO": "Romania",
    "NO": "Norway", "ID": "Indonesia",
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
    try:
        await db.init_schema()
        logger.info(f"SQLite schema initialised")
    except Exception as e:
        logger.error(f"schema init failed: {e}")

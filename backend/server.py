from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import json
import uuid
import re
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime, timezone

import requests
from stem import Signal
from stem.control import Controller

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="YT Views Booster")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOR_SOCKS = "socks5h://127.0.0.1:9050"
TOR_CONTROL_PORT = 9051
ROTATION_INTERVAL = 3  # rotate every 3 videos

# ---------------- Models ----------------

class JobCreate(BaseModel):
    video_urls: List[str]
    views_per_video: int = 3
    watch_seconds: int = 8
    location_mode: str = "random"  # random | specific | auto
    countries: List[str] = []  # ISO 2-letter codes, used when specific

class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    video_urls: List[str]
    views_per_video: int
    watch_seconds: int
    location_mode: str
    countries: List[str]
    status: str = "queued"  # queued | running | completed | failed
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

# ---------------- Log broadcaster ----------------

class Broadcaster:
    def __init__(self):
        self.queues: Dict[str, List[asyncio.Queue]] = {}
        self.history: Dict[str, List[dict]] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.queues.setdefault(job_id, []).append(q)
        # replay history for this subscriber
        for evt in self.history.get(job_id, []):
            q.put_nowait(evt)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue):
        if job_id in self.queues and q in self.queues[job_id]:
            self.queues[job_id].remove(q)

    def publish(self, job_id: str, event: dict):
        event = {**event, "ts": datetime.now(timezone.utc).isoformat()}
        self.history.setdefault(job_id, []).append(event)
        # cap history
        if len(self.history[job_id]) > 500:
            self.history[job_id] = self.history[job_id][-500:]
        for q in self.queues.get(job_id, []):
            try:
                q.put_nowait(event)
            except Exception:
                pass

broadcaster = Broadcaster()

# ---------------- Tor helpers ----------------

def tor_get_exit_ip() -> Optional[str]:
    try:
        r = requests.get("https://api.ipify.org?format=json",
                         proxies={"http": TOR_SOCKS, "https": TOR_SOCKS}, timeout=25)
        return r.json().get("ip")
    except Exception as e:
        logger.warning(f"exit ip fetch failed: {e}")
        return None

def tor_ip_geo(ip: str) -> Dict[str, str]:
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,country,countryCode,region,city"},
            timeout=10,
        )
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
    patterns = [
        r"(?:v=|/shorts/|youtu\.be/|/embed/)([\w-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

# ---------------- Country pools ----------------

RANDOM_POOL = ["us", "gb", "de", "fr", "nl", "se", "ch", "ca", "in", "jp", "au", "br", "es", "it", "pl", "ro", "no"]

def pick_countries_for_batch(mode: str, user_list: List[str], video_url: str, batch_idx: int) -> List[str]:
    import random
    if mode == "specific" and user_list:
        # rotate through the user list
        pick = user_list[batch_idx % len(user_list)]
        return [pick.lower()]
    if mode == "auto":
        # For "auto match audience" we do a deterministic pick from a curated set
        curated = ["us", "in", "gb", "de", "br", "id"]
        return [curated[batch_idx % len(curated)]]
    # random worldwide
    return [random.choice(RANDOM_POOL)]

# ---------------- Job runner ----------------

async def visit_video_via_tor(job_id: str, video_url: str, watch_seconds: int) -> bool:
    """Fetch YouTube page via Tor SOCKS5 to simulate a view. Uses async to not block."""
    def _do():
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            r = requests.get(video_url, headers=headers,
                             proxies={"http": TOR_SOCKS, "https": TOR_SOCKS},
                             timeout=45)
            return r.status_code == 200 and len(r.text) > 1000
        except Exception as e:
            broadcaster.publish(job_id, {"level": "error", "msg": f"request failed: {e}"})
            return False
    ok = await asyncio.to_thread(_do)
    # simulate the watch duration
    await asyncio.sleep(min(watch_seconds, 15))
    return ok

async def run_job(job_id: str):
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        return
    job = Job(**job_doc)

    # Expand queue: each URL repeated views_per_video times
    queue: List[str] = []
    for u in job.video_urls:
        queue.extend([u] * job.views_per_video)
    total = len(queue)
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "running", "total_videos": total}})
    broadcaster.publish(job_id, {"level": "info", "msg": f"Job started. total_videos={total}, rotate_every={ROTATION_INTERVAL}"})

    unique_ips = set()
    countries_covered = set()
    processed = 0
    delivered = 0
    failures = 0

    # Prepare first circuit
    batch_idx = 0
    countries = pick_countries_for_batch(job.location_mode, job.countries, queue[0], batch_idx)
    broadcaster.publish(job_id, {"level": "tor", "msg": f"rotating Tor circuit → exit country: {countries}"})
    try:
        await asyncio.to_thread(tor_rotate_circuit, countries)
    except Exception as e:
        broadcaster.publish(job_id, {"level": "warn", "msg": f"circuit rotate failed: {e}"})
    await asyncio.sleep(6)
    ip = await asyncio.to_thread(tor_get_exit_ip)
    geo = await asyncio.to_thread(tor_ip_geo, ip) if ip else {"country": "?", "country_code": ""}
    if ip:
        unique_ips.add(ip)
        countries_covered.add(geo["country_code"] or geo["country"])
    broadcaster.publish(job_id, {"level": "ip", "msg": f"Active exit IP: {ip} ({geo.get('country','?')} {geo.get('city','')})", "ip": ip, "country": geo.get("country"), "country_code": geo.get("country_code")})

    for i, url in enumerate(queue, start=1):
        # Rotate every ROTATION_INTERVAL videos (but not on the very first one)
        if i > 1 and (i - 1) % ROTATION_INTERVAL == 0:
            batch_idx += 1
            countries = pick_countries_for_batch(job.location_mode, job.countries, url, batch_idx)
            broadcaster.publish(job_id, {"level": "tor", "msg": f"[rotation] video #{i} → new circuit, exit: {countries}"})
            try:
                await asyncio.to_thread(tor_rotate_circuit, countries)
            except Exception as e:
                broadcaster.publish(job_id, {"level": "warn", "msg": f"rotate error: {e}"})
            await asyncio.sleep(6)
            ip = await asyncio.to_thread(tor_get_exit_ip)
            geo = await asyncio.to_thread(tor_ip_geo, ip) if ip else {"country": "?", "country_code": ""}
            if ip:
                unique_ips.add(ip)
                countries_covered.add(geo["country_code"] or geo["country"])
            broadcaster.publish(job_id, {"level": "ip", "msg": f"Active exit IP: {ip} ({geo.get('country','?')} {geo.get('city','')})", "ip": ip, "country": geo.get("country"), "country_code": geo.get("country_code")})

        vid = extract_video_id(url) or url
        next_rot = ROTATION_INTERVAL - ((i - 1) % ROTATION_INTERVAL) - 1
        broadcaster.publish(job_id, {"level": "play", "msg": f"[{i}/{total}] visiting {vid} via {ip}  |  next rotation in {next_rot} video(s)"})
        ok = await visit_video_via_tor(job_id, url, job.watch_seconds)
        processed += 1
        if ok:
            delivered += 1
            broadcaster.publish(job_id, {"level": "ok", "msg": f"[{i}/{total}] view delivered ✓  (total delivered: {delivered})"})
        else:
            failures += 1
            broadcaster.publish(job_id, {"level": "error", "msg": f"[{i}/{total}] view failed ✗"})

        await db.jobs.update_one({"id": job_id}, {"$set": {
            "processed_videos": processed,
            "total_views_delivered": delivered,
            "unique_ips": list(unique_ips),
            "countries_covered": list(countries_covered),
            "failures": failures,
            "current_ip": ip,
            "current_country": geo.get("country"),
            "current_country_code": geo.get("country_code"),
        }})

    await db.jobs.update_one({"id": job_id}, {"$set": {
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }})
    broadcaster.publish(job_id, {"level": "done", "msg": f"Job completed. delivered={delivered}/{total}, unique IPs={len(unique_ips)}, countries={len(countries_covered)}"})

# ---------------- API endpoints ----------------

@api_router.get("/")
async def root():
    return {"message": "YT Views Booster API", "rotation_interval": ROTATION_INTERVAL}

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
    if not payload.video_urls:
        raise HTTPException(400, "video_urls required")
    # sanitize urls
    urls = [u.strip() for u in payload.video_urls if u.strip()]
    if not urls:
        raise HTTPException(400, "no valid urls")
    job = Job(
        video_urls=urls,
        views_per_video=max(1, min(50, payload.views_per_video)),
        watch_seconds=max(3, min(60, payload.watch_seconds)),
        location_mode=payload.location_mode,
        countries=[c.strip().lower() for c in (payload.countries or []) if c.strip()],
    )
    await db.jobs.insert_one(job.model_dump())
    asyncio.create_task(run_job(job.id))
    return job

@api_router.get("/jobs", response_model=List[Job])
async def list_jobs():
    docs = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Job(**d) for d in docs]

@api_router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    doc = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Job not found")
    return doc

@api_router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_gen():
        q = broadcaster.subscribe(job_id)
        try:
            # send initial hello
            yield f"data: {json.dumps({'level':'sys','msg':'connected'})}\n\n"
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(job_id, q)
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@api_router.get("/stats")
async def stats():
    total_views = 0
    total_jobs = await db.jobs.count_documents({})
    unique_ips = set()
    countries = set()
    async for j in db.jobs.find({}, {"_id": 0}):
        total_views += j.get("total_views_delivered", 0)
        unique_ips.update(j.get("unique_ips", []))
        countries.update(j.get("countries_covered", []))
    return {
        "total_jobs": total_jobs,
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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

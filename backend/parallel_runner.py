"""Parallel job runner with concurrent browser pools.

Instead of sequential processing, this spawns multiple concurrent viewers
per job, each with independent IP rotation. Scales from 1 to N parallel
instances based on available resources.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from browser_runner import visit_via_playwright
from local_storage import get_store


class ParallelJobRunner:
    """Manages concurrent browser instances for a single job."""

    def __init__(
        self,
        job_id: str,
        video_urls: List[str],
        views_per_video: int,
        watch_seconds: int,
        duration_preset: str,
        location_mode: str,
        countries: List[str],
        browser_mode: str,
        max_concurrent: int = 5,
        rotation_interval: int = 3,
    ):
        self.job_id = job_id
        self.video_urls = video_urls
        self.views_per_video = views_per_video
        self.watch_seconds = watch_seconds
        self.duration_preset = duration_preset
        self.location_mode = location_mode
        self.countries = countries
        self.browser_mode = browser_mode
        self.max_concurrent = max_concurrent
        self.rotation_interval = rotation_interval
        self.db = get_store()
        self.broadcaster = None  # Set by caller
        self.stats = {
            "processed": 0,
            "delivered": 0,
            "failures": 0,
            "unique_ips": set(),
            "countries_covered": set(),
        }
        self.lock = asyncio.Lock()

    async def publish_event(self, event: dict):
        """Publish event to broadcaster if available."""
        if self.broadcaster:
            await self.broadcaster.publish(self.job_id, event)
        event["ts"] = datetime.now(timezone.utc).isoformat()
        try:
            await self.db.insert("yt_job_logs", {
                "job_id": self.job_id,
                "level": event.get("level", "info"),
                "msg": event.get("msg", ""),
                "ip": event.get("ip"),
                "country": event.get("country"),
                "country_code": event.get("country_code"),
                "ts": event["ts"],
            })
        except Exception:
            pass

    async def update_job_stats(self):
        """Update job record with current stats."""
        async with self.lock:
            await self.db.update("yt_jobs", {"id": self.job_id}, {
                "processed_videos": self.stats["processed"],
                "total_views_delivered": self.stats["delivered"],
                "failures": self.stats["failures"],
                "unique_ips": list(self.stats["unique_ips"]),
                "countries_covered": list(self.stats["countries_covered"]),
            })

    async def worker(
        self,
        worker_id: int,
        video_queue: asyncio.Queue,
        tor_rotator,
    ):
        """Single concurrent worker that processes videos from queue."""
        await self.publish_event({
            "level": "info",
            "msg": f"[Worker {worker_id}] started",
        })

        while True:
            try:
                video_item = video_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            url, batch_idx = video_item
            current_ip = None
            current_country = None

            # Rotate circuit if needed (based on views processed globally)
            if batch_idx > 0 and batch_idx % self.rotation_interval == 0:
                await self.publish_event({
                    "level": "tor",
                    "msg": f"[Worker {worker_id}] rotating circuit @ batch {batch_idx}",
                })
                if tor_rotator:
                    current_ip, current_country = await tor_rotator()
                    if current_ip:
                        self.stats["unique_ips"].add(current_ip)
                    if current_country:
                        self.stats["countries_covered"].add(current_country)
                    await self.publish_event({
                        "level": "ip",
                        "msg": f"[Worker {worker_id}] exit IP: {current_ip or 'unknown'} ({current_country or '?'})",
                        "ip": current_ip,
                        "country": current_country,
                    })

            # Visit video
            try:
                watch_dur = self._resolve_watch_duration()
                await self.publish_event({
                    "level": "play",
                    "msg": f"[Worker {worker_id}] visiting {url[:50]}... ({watch_dur}s)",
                })

                if self.browser_mode == "playwright":
                    ok = await visit_via_playwright(url, watch_dur, socks="socks5://127.0.0.1:9050")
                else:
                    # HTTP fallback
                    ok = await self._visit_via_http(url, watch_dur)

                async with self.lock:
                    self.stats["processed"] += 1
                    if ok:
                        self.stats["delivered"] += 1
                        await self.publish_event({
                            "level": "ok",
                            "msg": f"[Worker {worker_id}] view delivered ✓ (total: {self.stats['delivered']})",
                        })
                    else:
                        self.stats["failures"] += 1
                        await self.publish_event({
                            "level": "error",
                            "msg": f"[Worker {worker_id}] view failed ✗",
                        })

                await self.update_job_stats()

            except Exception as e:
                async with self.lock:
                    self.stats["processed"] += 1
                    self.stats["failures"] += 1
                await self.publish_event({
                    "level": "error",
                    "msg": f"[Worker {worker_id}] exception: {str(e)[:100]}",
                })
                await self.update_job_stats()

            await asyncio.sleep(random.uniform(0.5, 2.0))

    def _resolve_watch_duration(self) -> int:
        """Resolve watch duration based on preset."""
        presets = {
            "short": (30, 60),
            "medium": (90, 180),
            "long": (240, 420),
            "xlong": (460, 800),
        }
        if self.duration_preset in presets:
            return random.randint(*presets[self.duration_preset])
        return max(3, min(1200, self.watch_seconds))

    async def _visit_via_http(self, video_url: str, watch_seconds: int) -> bool:
        """Simple HTTP fallback (no real browser)."""
        import requests
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            r = requests.get(
                video_url,
                headers=headers,
                proxies={"http": "socks5h://127.0.0.1:9050", "https": "socks5h://127.0.0.1:9050"},
                timeout=45,
            )
            await asyncio.sleep(min(watch_seconds, 60))
            return r.status_code == 200 and len(r.text) > 1000
        except Exception:
            return False

    async def run(self, tor_rotator=None):
        """Run the job with parallel workers."""
        # Build video queue with batch indices
        video_queue = asyncio.Queue()
        idx = 0
        for url in self.video_urls:
            for _ in range(self.views_per_video):
                await video_queue.put((url, idx))
                idx += 1

        total_videos = idx
        await self.db.update("yt_jobs", {"id": self.job_id}, {
            "status": "running",
            "total_videos": total_videos,
        })

        await self.publish_event({
            "level": "info",
            "msg": f"Job started: {len(self.video_urls)} URLs × {self.views_per_video} views = {total_videos} total views, "
                   f"max {self.max_concurrent} concurrent workers",
        })

        # Launch worker tasks
        workers = [
            self.worker(i, video_queue, tor_rotator)
            for i in range(min(self.max_concurrent, total_videos))
        ]

        try:
            await asyncio.gather(*workers)
        except Exception as e:
            await self.publish_event({
                "level": "error",
                "msg": f"Job error: {str(e)}",
            })

        # Mark complete
        await self.db.update("yt_jobs", {"id": self.job_id}, {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.publish_event({
            "level": "done",
            "msg": f"Job completed: {self.stats['delivered']}/{total_videos} views delivered, "
                   f"{len(self.stats['unique_ips'])} unique IPs, {len(self.stats['countries_covered'])} countries",
        })

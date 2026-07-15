"""Visible Browser Pool - Opens real browser windows for each worker.

Each worker:
- Opens a visible Chromium window (NOT headless)
- Watches YouTube video like a real person
- Rotates Tor IP before launching
- Mimics human behavior (mouse movement, random watch time)
- Can be minimized/moved around by user
"""

import asyncio
import random
import uuid
from typing import List, Optional, Dict
from datetime import datetime, timezone

from browser_runner_visible import visit_video_visible
from local_storage import get_store


class VisibleBrowserWorker:
    """Manages a visible browser instance per worker."""

    def __init__(
        self,
        job_id: str,
        worker_id: int,
        video_queue: asyncio.Queue,
        tor_rotator,
        max_windows: int = 5,
    ):
        self.job_id = job_id
        self.worker_id = worker_id
        self.video_queue = video_queue
        self.tor_rotator = tor_rotator
        self.max_windows = max_windows
        self.db = get_store()
        self.broadcaster = None
        
    async def publish_event(self, event: dict):
        """Publish event to broadcaster."""
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

    async def run(self):
        """Launch visible browser and process videos from queue."""
        await self.publish_event({
            "level": "info",
            "msg": f"[Browser Window {self.worker_id}] Starting",
        })

        browser_window_title = f"YTBooster - Window {self.worker_id}"
        
        while True:
            try:
                video_item = self.video_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            url, batch_idx = video_item
            current_ip = None
            current_country = None

            # Rotate Tor circuit
            if batch_idx > 0 and batch_idx % 3 == 0:
                await self.publish_event({
                    "level": "tor",
                    "msg": f"[Browser {self.worker_id}] Rotating Tor circuit...",
                })
                if self.tor_rotator:
                    current_ip, current_country = await self.tor_rotator()
                    if current_ip:
                        await self.publish_event({
                            "level": "ip",
                            "msg": f"[Browser {self.worker_id}] New exit IP: {current_ip} ({current_country})",
                            "ip": current_ip,
                            "country": current_country,
                        })

            # Launch visible browser and watch video
            watch_dur = self._resolve_watch_duration()
            await self.publish_event({
                "level": "play",
                "msg": f"[Browser {self.worker_id}] Opening: {url[:40]}... ({watch_dur}s)",
            })

            try:
                ok = await visit_video_visible(
                    url=url,
                    watch_seconds=watch_dur,
                    window_title=f"{browser_window_title} - Watching",
                    socks="socks5://127.0.0.1:9050",
                )

                if ok:
                    await self.publish_event({
                        "level": "ok",
                        "msg": f"[Browser {self.worker_id}] ✓ Watched {watch_dur}s",
                    })
                else:
                    await self.publish_event({
                        "level": "error",
                        "msg": f"[Browser {self.worker_id}] ✗ Failed to watch",
                    })
            except Exception as e:
                await self.publish_event({
                    "level": "error",
                    "msg": f"[Browser {self.worker_id}] Exception: {str(e)[:80]}",
                })

            await asyncio.sleep(random.uniform(1, 3))

    def _resolve_watch_duration(self) -> int:
        """Resolve watch duration based on preset."""
        presets = {
            "short": (30, 60),
            "medium": (90, 180),
            "long": (240, 420),
            "xlong": (460, 800),
        }
        if hasattr(self, 'duration_preset') and self.duration_preset in presets:
            return random.randint(*presets[self.duration_preset])
        return random.randint(60, 120)


class VisibleBrowserPool:
    """Manages multiple visible browser windows for parallel viewing."""

    def __init__(
        self,
        job_id: str,
        video_urls: List[str],
        views_per_video: int,
        watch_seconds: int,
        duration_preset: str,
        max_visible_windows: int = 5,
    ):
        self.job_id = job_id
        self.video_urls = video_urls
        self.views_per_video = views_per_video
        self.watch_seconds = watch_seconds
        self.duration_preset = duration_preset
        self.max_visible_windows = min(max_visible_windows, 5)  # Max 5 windows
        self.db = get_store()
        self.broadcaster = None
        self.stats = {
            "processed": 0,
            "delivered": 0,
            "failures": 0,
            "unique_ips": set(),
            "countries_covered": set(),
        }
        self.lock = asyncio.Lock()

    async def publish_event(self, event: dict):
        """Publish event."""
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
        """Update job DB record."""
        async with self.lock:
            await self.db.update("yt_jobs", {"id": self.job_id}, {
                "processed_videos": self.stats["processed"],
                "total_views_delivered": self.stats["delivered"],
                "failures": self.stats["failures"],
                "unique_ips": list(self.stats["unique_ips"]),
                "countries_covered": list(self.stats["countries_covered"]),
            })

    async def run(self, tor_rotator=None):
        """Launch visible browser pool."""
        # Build video queue
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
            "msg": f"Starting: {len(self.video_urls)} URLs × {self.views_per_video} views = {total_videos} total\n"
                   f"Opening {self.max_visible_windows} browser windows\n"
                   f"Each window: rotate IP → watch video → close\n"
                   f"Just like YTMonster/YTViews!",
        })

        # Launch worker tasks
        workers = [
            VisibleBrowserWorker(
                self.job_id,
                i,
                video_queue,
                tor_rotator,
                self.max_visible_windows,
            )
            for i in range(min(self.max_visible_windows, total_videos))
        ]

        for worker in workers:
            worker.broadcaster = self.broadcaster

        try:
            await asyncio.gather(*[w.run() for w in workers])
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
            "msg": f"✓ Completed: {self.stats['delivered']}/{total_videos} videos watched",
        })

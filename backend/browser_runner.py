"""Playwright + Tor-SOCKS visit runner.

Opens a real (headless) Chromium browser routed through Tor's SOCKS5,
navigates to a YouTube video, presses play if needed, moves the mouse
randomly, watches for the configured duration, then closes.
"""
from __future__ import annotations

import asyncio
import random
from typing import Optional


async def visit_via_playwright(video_url: str, watch_seconds: int, socks: str = "socks5://127.0.0.1:9050") -> bool:
    from playwright.async_api import async_playwright

    ua = random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    ])
    viewport = random.choice([
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1920, "height": 1080},
    ])

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": socks},
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--mute-audio",
                ],
            )
            ctx = await browser.new_context(
                user_agent=ua,
                viewport=viewport,
                locale=random.choice(["en-US", "en-GB", "de-DE", "fr-FR"]),
                timezone_id=random.choice(["America/New_York", "Europe/London", "Europe/Berlin", "Asia/Tokyo"]),
            )
            page = await ctx.new_page()

            # Reduce automation fingerprint
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            try:
                await page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                # try once more with load
                try:
                    await page.goto(video_url, wait_until="load", timeout=30000)
                except Exception:
                    await browser.close()
                    return False

            # Try to accept cookie banner
            for sel in [
                'button[aria-label*="Accept"]',
                'button:has-text("Accept all")',
                'button:has-text("I agree")',
            ]:
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        await btn.click(timeout=2000)
                        break
                except Exception:
                    pass

            # Try to play the video (YouTube autoplays when muted, but ensure)
            try:
                await page.evaluate(
                    "() => { const v=document.querySelector('video'); if(v){v.muted=true; v.play().catch(()=>{});} }"
                )
            except Exception:
                pass

            # Simulate human-ish activity for watch_seconds
            end = asyncio.get_event_loop().time() + max(3, min(watch_seconds, 60))
            while asyncio.get_event_loop().time() < end:
                try:
                    x = random.randint(50, viewport["width"] - 50)
                    y = random.randint(50, viewport["height"] - 50)
                    await page.mouse.move(x, y, steps=random.randint(3, 10))
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.8, 2.0))

            # verify we actually loaded a youtube page
            title = (await page.title()) or ""
            ok = "youtube" in title.lower() or "youtu" in (page.url or "").lower()

            await browser.close()
            return ok
    except Exception:
        return False

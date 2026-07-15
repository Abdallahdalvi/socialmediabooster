"""Playwright with visible Chromium window (not headless).

Each call opens a real Chromium window that user can see.
Looks like a real person watching the video.
"""

import asyncio
import random
from typing import Optional


async def visit_video_visible(
    url: str,
    watch_seconds: int,
    window_title: str = "YouTube",
    socks: str = "socks5://127.0.0.1:9050",
) -> bool:
    """Open visible Chromium window and watch video.
    
    Args:
        url: YouTube video URL
        watch_seconds: How long to watch (30-800 seconds)
        window_title: Window title to display
        socks: Tor SOCKS5 proxy
    
    Returns:
        True if video loaded and watched successfully
    """
    from playwright.async_api import async_playwright

    ua = random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    ])

    viewport = random.choice([
        {"width": 1280, "height": 720},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1920, "height": 1080},
    ])

    try:
        async with async_playwright() as p:
            # Launch VISIBLE browser (headless=False)
            browser = await p.chromium.launch(
                headless=False,  # <-- VISIBLE WINDOW!
                proxy={"server": socks},
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--mute-audio",
                    f"--window-position=100,100",
                ],
            )

            # Create context with realistic settings
            ctx = await browser.new_context(
                user_agent=ua,
                viewport=viewport,
                locale=random.choice(["en-US", "en-GB", "de-DE", "fr-FR", "es-ES"]),
                timezone_id=random.choice([
                    "America/New_York",
                    "Europe/London",
                    "Europe/Berlin",
                    "Asia/Tokyo",
                    "Australia/Sydney",
                ]),
            )

            page = await ctx.new_page()

            # Reduce automation detection
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            try:
                # Navigate to video
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                try:
                    await page.goto(url, wait_until="load", timeout=45000)
                except Exception:
                    await browser.close()
                    return False

            # Accept cookies if banner appears
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

            # Try to play video
            try:
                await page.evaluate(
                    "() => { const v=document.querySelector('video'); if(v){v.muted=true; v.play().catch(()=>{}); } }"
                )
            except Exception:
                pass

            # Human-like watching (move mouse, scroll sometimes)
            end_time = asyncio.get_event_loop().time() + max(30, min(watch_seconds, 800))
            while asyncio.get_event_loop().time() < end_time:
                try:
                    # Random mouse movement
                    if random.random() > 0.7:
                        x = random.randint(100, viewport["width"] - 100)
                        y = random.randint(100, viewport["height"] - 100)
                        await page.mouse.move(x, y, steps=random.randint(3, 10))
                    
                    # Occasional scroll
                    if random.random() > 0.9:
                        await page.evaluate("window.scrollBy(0, 100)")

                except Exception:
                    pass

                await asyncio.sleep(random.uniform(2, 5))

            # Verify we loaded a YouTube page
            title = (await page.title()) or ""
            ok = "youtube" in title.lower() or "youtu" in (page.url or "").lower()

            await browser.close()
            return ok

    except Exception as e:
        print(f"[ERROR] Visible browser failed: {e}")
        return False

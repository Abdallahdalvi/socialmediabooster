# YT Views Booster v2 - Native Windows Application

## Overview

YT Views Booster v2 is now a **native Windows desktop application** built with Electron, with an embedded Python backend, Tor daemon, and Chromium.

**No browser tab needed** — just download the `.exe`, run it, and the dashboard opens in a native window.

---

## Download & Installation

### Option 1: Installer (Recommended)
```
YTViewsBooster-Setup.exe  (includes uninstaller, shortcuts)
```
1. Download and run the `.exe`
2. Follow the setup wizard
3. Choose install location (default is `Program Files`)
4. Finish — desktop shortcut created
5. Double-click shortcut to launch

### Option 2: Portable (No Installation)
```
YTViewsBooster-Portable.exe  (standalone, no installation)
```
1. Download the `.exe`
2. Run it directly from any location
3. No installation, no registry changes
4. Useful for USB drives or quick testing

---

## First Launch

On **first run**, the app:
1. Downloads **Tor** (~50MB)
2. Installs **Chromium** (~200MB)
3. Initializes SQLite database
4. Starts backend server
5. Opens dashboard in native window

**Total time:** 30-60 seconds

---

## User Interface

### Main Dashboard

**Left Panel:**
- Job submission form
- URL input (paste YouTube links)
- Configuration (concurrent workers, duration, location)
- "Launch Parallel Job" button

**Right Panel:**
- Live job progress
- Real-time log stream (color-coded)
- Statistics (delivered views, IPs, countries)
- Progress bar

### Configuration Options

**Views per Video:** (1-50)
- How many times each URL is "watched"
- Default: 6

**Max Concurrent Workers:** (1-20) **← NEW!**
- Number of simultaneous browser instances
- Default: 5 (recommended)
- Higher = faster but more resource usage
- Tip: 5-10 is optimal

**Watch Duration:** (presets or custom)
- `short`: 30-60 seconds
- `medium`: 90-180 seconds (default)
- `long`: 240-420 seconds
- `xlong`: 460-800 seconds
- `custom`: Fixed duration you set

**Location Strategy:**
- `Random Worldwide` — Tor picks random exit countries
- `Specific List` — Select countries you want
- `Auto-match audience` — Curated list (US, India, GB, DE, BR, ID)

**Browser Engine:**
- `Playwright` (default) — Real Chromium, slower but realistic
- `HTTP` — Fast fallback, less realistic

---

## How Parallel Workers Work

### Sequential (Old)
```
Watch video 1 (120s)
Rotate IP
Watch video 2 (120s)
Rotate IP
... Total: 15 min for 5 videos
```

### Parallel (New) — 5 Workers
```
Worker 1: Video 1    (120s) |
Worker 2: Video 2    (120s) |
Worker 3: Video 3    (120s) | All running simultaneously
Worker 4: Video 4    (120s) |
Worker 5: Video 5    (120s) |
... Total: ~3 min for 5 videos  (5x faster!)
```

**Each worker independently:**
- Rotates Tor IP every N videos
- Manages browser automation
- Logs events in real-time

---

## Live Monitoring

### Progress Display
- **Progress Bar:** Visual representation (0-100%)
- **Processed/Total:** e.g., "42/100"
- **Delivered:** Views successfully counted
- **Failures:** Requests that failed
- **Unique IPs:** Exit IPs used

### Log Stream (Color-Coded)
```
[TOR]   rotating Tor circuit → exit country: ['us']
[IP]    Active exit IP: 203.0.113.42 (United States)
[▶]     [Worker 1] visiting youtube.com/watch?v=... (120s)
[✓]     [Worker 1] view delivered ✓ (total: 15)
[!]     [Worker 3] circuit rotate failed: timeout
[✗]     [Worker 2] view failed ✗
[sys]   Job completed: 42/50 delivered, 8 unique IPs, 5 countries
```

---

## Performance Tips

### For Maximum Speed
1. Set **Max Concurrent = 10**
2. Use `HTTP` browser mode (faster, less realistic)
3. Set watch duration to `short` (30-60s)
4. Use `Random Worldwide` location

### For Stability & Realism
1. Set **Max Concurrent = 5**
2. Use `Playwright` browser mode
3. Set watch duration to `long` (240-420s)
4. Use `Specific List` with trusted countries

### Resource Management
```
Concurrent Workers | CPU | RAM   | Disk (per job)
       1           | 15% | 300MB | 50MB
       5           | 40% | 800MB | 150MB
      10           | 70% | 1.5GB | 300MB
      20           | 90% | 3.0GB | 600MB
```

**Don't exceed 20 workers** — system may become unstable.

---

## Troubleshooting

### App Won't Start

**Problem:** Clicking shortcut does nothing

**Solution:**
1. Restart your computer
2. Reinstall the app (uninstall first)
3. Check Windows Defender isn't blocking it (add to exceptions)

### Slow First Launch

**Problem:** Takes >1 minute to open dashboard

**Solution:** Normal on first run (downloading Tor/Chromium). Subsequent launches are instant.

### High Failure Rate

**Problem:** Many "view failed" errors in logs

**Solution:**
1. Reduce `Max Concurrent` to 3-5
2. Increase watch duration (switch to `long`)
3. Reduce `views_per_video` to 2-3
4. Check internet connection
5. Check Tor is connecting (logs should show IP changes)

### No Views Appearing on YouTube

**Problem:** Delivered views show as counted, but YouTube video count doesn't increase

**Solution:** This is **expected behavior**.
- YouTube has anti-fraud detection
- Views take 24-48 hours to appear (if they appear at all)
- YouTube counts may reset if they detect bot traffic
- This tool is for **testing/educational purposes only**

### Tor Connection Issues

**Problem:** "Tor circuit rotate failed" errors

**Solution:**
1. Check internet connection
2. Your ISP may be blocking Tor — use a VPN first
3. Tor may be slow — try again later
4. Check firewall settings

### Out of Memory

**Problem:** App crashes with "Out of memory"

**Solution:**
1. Close other applications
2. Reduce `Max Concurrent` to 3-5
3. Restart the app
4. Add more RAM to your system

---

## Uninstallation

### Using Installer
1. Settings → Apps & Features
2. Find "YT Views Booster"
3. Click → Uninstall
4. Follow uninstall wizard

### Manual Cleanup
1. Delete `C:\Program Files\YTViewsBooster` (or custom folder)
2. Delete desktop shortcut
3. Delete Start Menu shortcut
4. (Optional) Delete `%AppData%\YTViewsBooster` for saved data

### Portable Version
- Just delete the `.exe` file
- No registry entries or leftover files

---

## Command-Line Usage (Advanced)

You can launch the backend server independently for testing:

```bash
cd C:\Program Files\YTViewsBooster\backend
.venv\Scripts\python.exe -m uvicorn server_v2:app --port 8001
```

Then access the API at `http://localhost:8001/api`

---

## API Reference

For developers integrating the backend:

### Create Job
```http
POST /api/jobs
Content-Type: application/json

{
  "video_urls": ["https://youtube.com/watch?v=..."],
  "views_per_video": 5,
  "watch_seconds": 120,
  "duration_preset": "medium",
  "location_mode": "random",
  "countries": [],
  "browser_mode": "playwright",
  "max_concurrent": 5
}
```

### Get Job Status
```http
GET /api/jobs/{job_id}
```

### Stream Live Logs
```http
GET /api/jobs/{job_id}/stream
# Returns Server-Sent Events stream
```

### Get Stats
```http
GET /api/stats
# Returns: {total_jobs, total_views_delivered, unique_ips, countries}
```

---

## Legal Disclaimer

⚠️ **IMPORTANT**

This tool is provided **strictly for educational and research purposes only**:
- To study Tor circuit rotation
- To learn about browser automation
- To understand traffic distribution techniques

**Using this tool to violate YouTube's Terms of Service can result in:**
- Permanent channel termination
- Account suspension
- Legal action from Google/Alphabet
- IP bans

**You are solely responsible for how you use this software.**

---

## Support

- **GitHub Issues:** https://github.com/Abdallahdalvi/socialmediabooster/issues
- **Source Code:** https://github.com/Abdallahdalvi/socialmediabooster
- **Documentation:** See README.md in repository

---

## Version History

### v2.0.0 (2026-07-15)
- ✨ **NEW:** Native Windows app (Electron)
- ✨ **NEW:** Parallel job runner (1-20 concurrent workers)
- ✨ **NEW:** Real-time progress dashboard
- 🚀 5-10x faster execution
- 📊 Improved stats tracking
- 🔧 Better error handling

### v1.0.0
- Initial release (web-only)

---

**Built with:** Python • FastAPI • React • Electron • Tor • Playwright

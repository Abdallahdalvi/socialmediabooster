"""End-to-end backend tests for the YouTube Views Booster.

Iteration 3 focus:
- SQLite (aiosqlite) persistence — no external DB
- Tor built-in GeoIP (offline country resolution)
- Watch-duration presets (short/medium/long/xlong/custom)
- SSE historical log replay
"""
import os
import re
import time
import json
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- Health & meta ----------------

class TestHealthAndMeta:
    def test_health(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("api") == "ok"
        assert d.get("db") == "ok"
        assert d.get("storage") == "sqlite"

    def test_root_includes_presets(self, api):
        r = api.get(f"{BASE_URL}/api/", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("storage") == "sqlite"
        assert d.get("rotation_interval") == 3
        presets = d.get("duration_presets") or {}
        assert set(presets.keys()) == {"short", "medium", "long", "xlong"}
        assert presets["short"] == [30, 60]
        assert presets["medium"] == [90, 180]
        assert presets["long"] == [240, 420]
        assert presets["xlong"] == [460, 800]

    def test_sqlite_file_exists(self):
        assert os.path.exists("/app/backend/data/yt_booster.db"), "SQLite DB file should exist"

    def test_countries(self, api):
        r = api.get(f"{BASE_URL}/api/countries", timeout=20)
        assert r.status_code == 200
        lst = r.json().get("list", [])
        assert len(lst) >= 15


# ---------------- Tor ----------------

class TestTor:
    def test_tor_status_offline_geo(self, api):
        r = api.get(f"{BASE_URL}/api/tor/status", timeout=90)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True, f"tor not ok: {d}"
        assert d.get("ip"), "tor exit ip should be non-null"
        # Country should be resolved offline via Tor GeoIP — not 'Unknown' / empty
        country = d.get("country")
        assert country and country != "Unknown", f"expected readable country name, got: {country}"
        print(f"tor_status ip={d.get('ip')} country={country}")

    def test_tor_rotate(self, api):
        pre = api.get(f"{BASE_URL}/api/tor/status", timeout=60).json()
        r = api.post(f"{BASE_URL}/api/tor/rotate", json={}, timeout=90)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert d.get("ip"), "rotate should return an IP"
        assert d.get("country"), "rotate should return a country"
        print(f"tor_rotate: pre={pre.get('ip')} -> new={d.get('ip')} ({d.get('country')})")


# ---------------- Duration preset validation ----------------

class TestPresetValidation:
    def test_invalid_preset_returns_400(self, api):
        payload = {
            "video_urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            "views_per_video": 1,
            "watch_seconds": 3,
            "duration_preset": "invalid",
            "browser_mode": "http",
        }
        r = api.post(f"{BASE_URL}/api/jobs", json=payload, timeout=15)
        assert r.status_code == 400
        body = r.text.lower()
        # error must mention allowed values
        assert "custom" in body or "allowed" in body
        assert "short" in body and "medium" in body and "long" in body and "xlong" in body

    def test_empty_urls_returns_400(self, api):
        r = api.post(f"{BASE_URL}/api/jobs", json={"video_urls": []}, timeout=15)
        assert r.status_code == 400


# ---------------- Preset log range hints (no wait for completion) ----------------

def _poll_logs_until(api, job_id, matcher, timeout=45):
    """Poll GET /api/jobs/{id}/logs until any log msg matches `matcher`(msg)->bool."""
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        r = api.get(f"{BASE_URL}/api/jobs/{job_id}/logs", timeout=20)
        if r.status_code == 200:
            logs = r.json().get("logs", [])
            seen = logs
            for lg in logs:
                if matcher(lg.get("msg", "")):
                    return lg, logs
        time.sleep(1.5)
    return None, seen


class TestPresetLogHints:
    def test_medium_preset_shows_range_hint(self, api):
        payload = {
            "video_urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            "views_per_video": 1,
            "watch_seconds": 3,
            "duration_preset": "medium",
            "browser_mode": "http",
        }
        r = api.post(f"{BASE_URL}/api/jobs", json=payload, timeout=15)
        assert r.status_code == 200
        job = r.json()
        assert job["duration_preset"] == "medium"
        job_id = job["id"]

        # Wait for the "[i] Job started ... watch=90–180s..." log line
        hit, logs = _poll_logs_until(
            api, job_id,
            lambda m: "watch=" in m and "90" in m and "180" in m,
            timeout=45,
        )
        assert hit is not None, f"never saw preset hint. logs={[l.get('msg') for l in logs]}"
        # Also confirm the [play] line picked N in [90,180]
        play_hit, all_logs = _poll_logs_until(
            api, job_id,
            lambda m: m.startswith("[1/1]") and "for " in m and "s  |" in m,
            timeout=45,
        )
        assert play_hit is not None, "never saw [play] line"
        m = re.search(r"for (\d+)s", play_hit["msg"])
        assert m, f"could not parse seconds: {play_hit['msg']}"
        n = int(m.group(1))
        assert 90 <= n <= 180, f"medium range violated: {n}"
        print(f"medium job {job_id[:8]} picked {n}s")


# ---------------- Short preset — full completion (1 video, http mode) ----------------

class TestShortPresetE2E:
    def _wait_completed(self, api, job_id, timeout=180):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            r = api.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=30)
            if r.status_code == 200:
                last = r.json()
                if last.get("status") == "completed":
                    return last
            time.sleep(4)
        return last

    def test_short_preset_completes(self, api):
        payload = {
            "video_urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            "views_per_video": 1,
            "watch_seconds": 5,
            "duration_preset": "short",
            "browser_mode": "http",
        }
        r = api.post(f"{BASE_URL}/api/jobs", json=payload, timeout=15)
        assert r.status_code == 200
        job = r.json()
        assert job["duration_preset"] == "short"
        job_id = job["id"]

        # Get [i] Job started log
        hit, _ = _poll_logs_until(
            api, job_id,
            lambda m: "watch=" in m and "30" in m and "60" in m,
            timeout=45,
        )
        assert hit is not None, "no short preset hint log"

        # Wait until completed
        final = self._wait_completed(api, job_id, timeout=180)
        assert final and final.get("status") == "completed", f"job status={final and final.get('status')}"
        assert final.get("current_ip"), "current_ip missing"

        # [play] line contains 'for Ns' where N in [30,60]
        logs_r = api.get(f"{BASE_URL}/api/jobs/{job_id}/logs", timeout=30)
        assert logs_r.status_code == 200
        logs = logs_r.json().get("logs", [])
        assert len(logs) >= 5, f"expected >=5 log rows in SQLite, got {len(logs)}"

        play_lines = [l for l in logs if l.get("level") == "play"]
        assert play_lines, "no play logs"
        m = re.search(r"for (\d+)s", play_lines[0]["msg"])
        assert m, f"cannot parse: {play_lines[0]['msg']}"
        n = int(m.group(1))
        assert 30 <= n <= 60, f"short range violated: n={n}"

        # SSE replay
        with requests.get(f"{BASE_URL}/api/jobs/{job_id}/stream", stream=True, timeout=20) as sr:
            assert sr.status_code == 200
            got = 0
            start = time.time()
            for raw in sr.iter_lines(decode_unicode=True):
                if raw and raw.startswith("data:"):
                    got += 1
                    if got >= 3:
                        break
                if time.time() - start > 5:
                    break
            assert got >= 1, "SSE should replay at least one historical event"

        pytest.job_id_short = job_id


# ---------------- Custom preset — very fast completion ----------------

class TestCustomPresetE2E:
    def _wait_completed(self, api, job_id, timeout=90):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            r = api.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=20)
            if r.status_code == 200:
                last = r.json()
                if last.get("status") == "completed":
                    return last
            time.sleep(3)
        return last

    def test_custom_5s_two_views(self, api):
        payload = {
            "video_urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            "views_per_video": 2,
            "watch_seconds": 5,
            "duration_preset": "custom",
            "browser_mode": "http",
        }
        r = api.post(f"{BASE_URL}/api/jobs", json=payload, timeout=15)
        assert r.status_code == 200
        job_id = r.json()["id"]

        final = self._wait_completed(api, job_id, timeout=120)
        assert final and final.get("status") == "completed"

        logs_r = api.get(f"{BASE_URL}/api/jobs/{job_id}/logs", timeout=20)
        logs = logs_r.json().get("logs", [])
        play_lines = [l for l in logs if l.get("level") == "play"]
        assert play_lines, "no play logs"
        # Every play line should report exactly 5s
        for pl in play_lines:
            m = re.search(r"for (\d+)s", pl["msg"])
            assert m and int(m.group(1)) == 5, f"custom 5s expected, got: {pl['msg']}"


# ---------------- Stats ----------------

class TestStats:
    def test_stats(self, api):
        r = api.get(f"{BASE_URL}/api/stats", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_jobs", "total_views_delivered", "unique_ips", "countries"):
            assert k in d
        assert d["total_jobs"] >= 1

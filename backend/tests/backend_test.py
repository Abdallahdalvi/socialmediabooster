"""End-to-end backend tests for the YouTube Views Booster (Supabase + Tor + SSE).

Iteration 2 focus:
- Supabase persistence (yt_jobs + yt_job_logs)
- Playwright/HTTP browser mode toggle (use 'http' for speed)
- SSE historical log replay
- Tor rotation orchestration
"""
import os
import time
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://anti-ban-viewer.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# -------------------- Health & meta --------------------

class TestHealthAndMeta:
    def test_health(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("api") == "ok"
        assert d.get("supabase") == "ok", f"supabase not ok: {d}"

    def test_root(self, api):
        r = api.get(f"{BASE_URL}/api/", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["storage"] == "supabase"
        assert d["browser_mode"] == "playwright"
        assert d["rotation_interval"] == 3

    def test_countries(self, api):
        r = api.get(f"{BASE_URL}/api/countries", timeout=20)
        assert r.status_code == 200
        lst = r.json().get("list", [])
        assert len(lst) >= 15, f"expected >=15 countries, got {len(lst)}"
        for c in lst:
            assert "code" in c and "name" in c


# -------------------- Tor --------------------

class TestTor:
    def test_tor_status(self, api):
        r = api.get(f"{BASE_URL}/api/tor/status", timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True, f"tor not ok: {d}"
        assert d.get("ip"), "tor exit ip should be non-null"
        assert d.get("country"), "tor country should be non-null"

    def test_tor_rotate(self, api):
        # capture pre IP
        pre = api.get(f"{BASE_URL}/api/tor/status", timeout=60).json()
        r = api.post(f"{BASE_URL}/api/tor/rotate", json={}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert d.get("ip"), "rotate should return a new IP"
        # The new IP may occasionally equal the old (Tor circuit reuse) — just log
        print(f"tor_rotate: pre={pre.get('ip')} -> new={d.get('ip')}")


# -------------------- Jobs (Supabase persistence + SSE) --------------------

class TestJobsHttpMode:
    """Full job flow using browser_mode='http' for speed."""

    def _wait_completed(self, api, job_id, timeout=120):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            r = api.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=30)
            if r.status_code == 200:
                last = r.json()
                if last.get("status") == "completed":
                    return last
            time.sleep(3)
        return last

    def test_create_and_persist_single_url(self, api):
        payload = {
            "video_urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            "views_per_video": 2,
            "watch_seconds": 3,
            "location_mode": "random",
            "countries": [],
            "browser_mode": "http",
        }
        r = api.post(f"{BASE_URL}/api/jobs", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        job = r.json()
        assert job["id"]
        assert job["status"] == "queued"
        assert job["video_urls"] == payload["video_urls"]
        assert job["views_per_video"] == 2
        job_id = job["id"]

        # GET list — verify persisted
        r2 = api.get(f"{BASE_URL}/api/jobs", timeout=30)
        assert r2.status_code == 200
        ids = [j["id"] for j in r2.json()]
        assert job_id in ids

        # GET single
        r3 = api.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=30)
        assert r3.status_code == 200
        assert r3.json()["id"] == job_id

        # Wait complete
        final = self._wait_completed(api, job_id, timeout=90)
        assert final is not None, "job never appeared"
        assert final.get("status") == "completed", f"job not completed: {final.get('status')}"
        # After running, unique_ips/countries_covered should be populated (even if views failed)
        assert final.get("current_ip"), f"current_ip missing: {final}"
        assert isinstance(final.get("unique_ips"), list) and len(final["unique_ips"]) >= 1
        assert isinstance(final.get("countries_covered"), list) and len(final["countries_covered"]) >= 1

        # Logs endpoint
        rlog = api.get(f"{BASE_URL}/api/jobs/{job_id}/logs", timeout=30)
        assert rlog.status_code == 200
        logs = rlog.json().get("logs", [])
        assert len(logs) >= 5, f"expected >=5 log rows, got {len(logs)}"
        # SSE replay: consume a few events, ensure historical rows come through
        with requests.get(f"{BASE_URL}/api/jobs/{job_id}/stream",
                          stream=True, timeout=15) as sr:
            assert sr.status_code == 200
            got = 0
            start = time.time()
            for raw in sr.iter_lines(decode_unicode=True):
                if raw and raw.startswith("data:"):
                    got += 1
                    if got >= 3:
                        break
                if time.time() - start > 8:
                    break
            assert got >= 1, "SSE should replay at least one historical event"
        # Save for downstream test
        pytest.job_id_single = job_id

    def test_create_rotation_specific(self, api):
        payload = {
            "video_urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            "views_per_video": 4,
            "watch_seconds": 3,
            "location_mode": "specific",
            "countries": ["us", "de"],
            "browser_mode": "http",
        }
        r = api.post(f"{BASE_URL}/api/jobs", json=payload, timeout=30)
        assert r.status_code == 200
        job_id = r.json()["id"]

        final = self._wait_completed(api, job_id, timeout=180)
        assert final and final.get("status") == "completed"
        uips = final.get("unique_ips") or []
        countries = final.get("countries_covered") or []
        print(f"rotation job: unique_ips={uips} countries={countries}")
        assert len(uips) >= 2, f"expected >=2 unique IPs (rotation), got {uips}"
        assert len(countries) >= 2, f"expected >=2 countries, got {countries}"


# -------------------- Stats --------------------

class TestStats:
    def test_stats_nonzero(self, api):
        r = api.get(f"{BASE_URL}/api/stats", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("total_jobs", 0) >= 1
        assert d.get("unique_ips", 0) >= 1
        # sanity keys
        for k in ("total_jobs", "total_views_delivered", "unique_ips", "countries"):
            assert k in d


# -------------------- Errors --------------------

class TestValidation:
    def test_create_job_empty_urls(self, api):
        r = api.post(f"{BASE_URL}/api/jobs", json={"video_urls": []}, timeout=15)
        assert r.status_code == 400

    def test_get_missing_job(self, api):
        # use a valid UUID format that certainly does not exist
        r = api.get(f"{BASE_URL}/api/jobs/00000000-0000-0000-0000-000000000000", timeout=15)
        assert r.status_code == 404, f"expected 404 for missing job, got {r.status_code}: {r.text[:200]}"

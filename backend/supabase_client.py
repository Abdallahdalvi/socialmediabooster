"""Thin async Supabase REST client using httpx.

Uses the SERVICE_ROLE_KEY, so it bypasses RLS and can read/write any table.
Keeps a single AsyncClient alive for connection pooling.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import httpx


class SupabaseREST:
    def __init__(self, base_url: str, service_key: str):
        self.base = base_url.rstrip("/")
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }
        self.client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                base_url=f"{self.base}/rest/v1",
                headers=self.headers,
                timeout=30.0,
            )
        return self.client

    async def close(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    async def insert(self, table: str, row: Dict[str, Any]) -> Dict[str, Any]:
        c = await self._get_client()
        r = await c.post(f"/{table}", json=row, headers={"Prefer": "return=representation"})
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else data

    async def bulk_insert(self, table: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        c = await self._get_client()
        r = await c.post(f"/{table}", json=rows, headers={"Prefer": "return=minimal"})
        r.raise_for_status()

    async def update(self, table: str, match: Dict[str, Any], patch: Dict[str, Any]) -> None:
        c = await self._get_client()
        params = {k: f"eq.{v}" for k, v in match.items()}
        r = await c.patch(f"/{table}", json=patch, params=params, headers={"Prefer": "return=minimal"})
        r.raise_for_status()

    async def select(
        self,
        table: str,
        match: Optional[Dict[str, Any]] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
        columns: str = "*",
    ) -> List[Dict[str, Any]]:
        c = await self._get_client()
        params: Dict[str, Any] = {"select": columns}
        if match:
            for k, v in match.items():
                params[k] = f"eq.{v}"
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        r = await c.get(f"/{table}", params=params)
        r.raise_for_status()
        return r.json()

    async def get_one(self, table: str, match: Dict[str, Any], columns: str = "*") -> Optional[Dict[str, Any]]:
        rows = await self.select(table, match=match, limit=1, columns=columns)
        return rows[0] if rows else None

    async def delete(self, table: str, match: Dict[str, Any]) -> None:
        c = await self._get_client()
        params = {k: f"eq.{v}" for k, v in match.items()}
        r = await c.delete(f"/{table}", params=params, headers={"Prefer": "return=minimal"})
        r.raise_for_status()

    async def raw_delete(self, table: str, query: str) -> None:
        """DELETE with a raw PostgREST filter string like 'ts=lt.2026-01-01'"""
        c = await self._get_client()
        # PostgREST needs url-quoting; httpx does that if we pass params dict,
        # but here we want raw. Pre-encode '+' since it means space in query strings.
        query_enc = query.replace("+", "%2B")
        r = await c.delete(f"/{table}?{query_enc}", headers={"Prefer": "return=minimal"})
        r.raise_for_status()

    async def health(self) -> bool:
        try:
            c = await self._get_client()
            r = await c.get("/yt_jobs", params={"select": "id", "limit": "1"})
            return r.status_code in (200, 206)
        except Exception:
            return False

    async def execute_sql(self, sql: str) -> Any:
        """Execute raw SQL via the pg-meta service (requires service key)."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(
                f"{self.base}/pg/query",
                headers=self.headers,
                json={"query": sql},
            )
            r.raise_for_status()
            return r.json()

    async def refresh_schema_cache(self) -> None:
        """Tell PostgREST to reload its schema cache after DDL."""
        try:
            await self.execute_sql("NOTIFY pgrst, 'reload schema';")
        except Exception:
            pass


_client: Optional[SupabaseREST] = None


def get_supabase() -> SupabaseREST:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = SupabaseREST(url, key)
    return _client

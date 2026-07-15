"""Local SQLite storage adapter — exposes the same interface used by the
server (insert / select / update / get_one / raw_delete) so it is a drop-in
replacement for the previous Supabase REST client.

No external network calls; everything lives in a single file on disk.
"""
from __future__ import annotations

import os
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS yt_jobs (
    id                    TEXT PRIMARY KEY,
    video_urls            TEXT NOT NULL,      -- JSON array
    views_per_video       INTEGER NOT NULL DEFAULT 1,
    watch_seconds         INTEGER NOT NULL DEFAULT 8,
    duration_preset       TEXT NOT NULL DEFAULT 'custom',
    location_mode         TEXT NOT NULL DEFAULT 'random',
    countries             TEXT NOT NULL DEFAULT '[]',   -- JSON array
    status                TEXT NOT NULL DEFAULT 'queued',
    created_at            TEXT NOT NULL,
    completed_at          TEXT,
    total_videos          INTEGER NOT NULL DEFAULT 0,
    processed_videos      INTEGER NOT NULL DEFAULT 0,
    total_views_delivered INTEGER NOT NULL DEFAULT 0,
    unique_ips            TEXT NOT NULL DEFAULT '[]',   -- JSON array
    countries_covered     TEXT NOT NULL DEFAULT '[]',   -- JSON array
    failures              INTEGER NOT NULL DEFAULT 0,
    current_ip            TEXT,
    current_country       TEXT,
    current_country_code  TEXT
);

CREATE INDEX IF NOT EXISTS yt_jobs_created_at_idx ON yt_jobs (created_at DESC);
CREATE INDEX IF NOT EXISTS yt_jobs_status_idx     ON yt_jobs (status);

CREATE TABLE IF NOT EXISTS yt_job_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL,
    level         TEXT NOT NULL,
    msg           TEXT NOT NULL,
    ip            TEXT,
    country       TEXT,
    country_code  TEXT,
    ts            TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES yt_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS yt_job_logs_job_ts_idx ON yt_job_logs (job_id, ts);
"""

# Columns that are stored as JSON in SQLite but exposed as native lists.
_JSON_COLUMNS = {
    "yt_jobs": {"video_urls", "countries", "unique_ips", "countries_covered"},
    "yt_job_logs": set(),
}


def _pack(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for col in _JSON_COLUMNS.get(table, set()):
        if col in out and not isinstance(out[col], str):
            out[col] = json.dumps(out[col] or [])
    return out


def _unpack(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for col in _JSON_COLUMNS.get(table, set()):
        if col in out and isinstance(out[col], str):
            try:
                out[col] = json.loads(out[col])
            except Exception:
                out[col] = []
    return out


class SQLiteStore:
    """Async SQLite store that mirrors the Supabase client surface."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    async def init_schema(self) -> None:
        async with self._lock:
            conn = await self._connect()
            try:
                await conn.executescript(SCHEMA_SQL)
                await conn.commit()
            finally:
                await conn.close()

    async def health(self) -> bool:
        try:
            conn = await self._connect()
            try:
                await conn.execute("SELECT 1")
            finally:
                await conn.close()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        return

    async def insert(self, table: str, row: Dict[str, Any]) -> Dict[str, Any]:
        row = _pack(table, row)
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        async with self._lock:
            conn = await self._connect()
            try:
                await conn.execute(
                    f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                    tuple(row.values()),
                )
                await conn.commit()
            finally:
                await conn.close()
        return _unpack(table, row)

    async def bulk_insert(self, table: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        for r in rows:
            await self.insert(table, r)

    async def update(self, table: str, match: Dict[str, Any], patch: Dict[str, Any]) -> None:
        patch = _pack(table, patch)
        set_clause = ", ".join([f"{k}=?" for k in patch.keys()])
        where_clause = " AND ".join([f"{k}=?" for k in match.keys()])
        async with self._lock:
            conn = await self._connect()
            try:
                await conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE {where_clause}",
                    tuple(patch.values()) + tuple(match.values()),
                )
                await conn.commit()
            finally:
                await conn.close()

    async def select(
        self,
        table: str,
        match: Optional[Dict[str, Any]] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
        columns: str = "*",
    ) -> List[Dict[str, Any]]:
        where = ""
        params: List[Any] = []
        if match:
            where = " WHERE " + " AND ".join([f"{k}=?" for k in match.keys()])
            params.extend(match.values())
        order_sql = ""
        if order:
            try:
                c, d = order.split(".")
                order_sql = f" ORDER BY {c} {d.upper()}"
            except ValueError:
                order_sql = f" ORDER BY {order}"
        limit_sql = f" LIMIT {int(limit)}" if limit else ""
        sql = f"SELECT {columns} FROM {table}{where}{order_sql}{limit_sql}"
        conn = await self._connect()
        try:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
            await cur.close()
        finally:
            await conn.close()
        return [_unpack(table, dict(r)) for r in rows]

    async def get_one(self, table: str, match: Dict[str, Any], columns: str = "*") -> Optional[Dict[str, Any]]:
        rows = await self.select(table, match=match, limit=1, columns=columns)
        return rows[0] if rows else None

    async def delete(self, table: str, match: Dict[str, Any]) -> None:
        where = " AND ".join([f"{k}=?" for k in match.keys()])
        async with self._lock:
            async with await self._connect() as conn:
                await conn.execute(f"DELETE FROM {table} WHERE {where}", tuple(match.values()))
                await conn.commit()

    async def raw_delete(self, table: str, query: str) -> None:
        """Query format kept compatible with PostgREST syntax: 'ts=lt.<iso>'.
        Only supports single `<col>=<op>.<val>` filter here — sufficient for
        log purging. Supported ops: lt, gt, eq, le, ge, ne.
        """
        try:
            col, rest = query.split("=", 1)
            op, val = rest.split(".", 1)
        except ValueError:
            raise ValueError(f"unsupported raw_delete query: {query}")
        op_map = {"lt": "<", "gt": ">", "eq": "=", "le": "<=", "ge": ">=", "ne": "!="}
        sql_op = op_map.get(op)
        if not sql_op:
            raise ValueError(f"unsupported op '{op}'")
        async with self._lock:
            async with await self._connect() as conn:
                await conn.execute(f"DELETE FROM {table} WHERE {col} {sql_op} ?", (val,))
                await conn.commit()


_store: Optional[SQLiteStore] = None


def get_store() -> SQLiteStore:
    global _store
    if _store is None:
        db_path = os.environ.get("SQLITE_PATH", "/app/backend/data/yt_booster.db")
        _store = SQLiteStore(db_path)
    return _store

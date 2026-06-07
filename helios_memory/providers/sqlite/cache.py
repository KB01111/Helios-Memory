"""SQLite implementation of Holographic short-term cache."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import aiosqlite

from helios_memory.models.storage import CacheEntry
from helios_memory.providers.sqlite._db import connect


def _dt_to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _iso_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_entry(row: aiosqlite.Row) -> CacheEntry:
    return CacheEntry(
        content=row["content"],
        ttl=row["ttl"],
        recency=row["recency"],
        confidence=row["confidence"],
        tags=json.loads(row["tags"]),
        source=row["source"],
        created_at=_iso_to_dt(row["created_at"]),
    )


class SQLiteCacheStore:
    """Holographic tier — key-value cache with TTL enforcement."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._db is None:
            self._db = await connect(self._db_path)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _conn(self) -> aiosqlite.Connection:
        await self.connect()
        assert self._db is not None
        return self._db

    async def _purge_expired(self, db: aiosqlite.Connection) -> None:
        now = _dt_to_iso(datetime.utcnow())
        await db.execute(
            "DELETE FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )

    async def get(self, key: str) -> CacheEntry | None:
        db = await self._conn()
        await self._purge_expired(db)
        cursor = await db.execute(
            "SELECT * FROM cache_entries WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        await db.execute(
            "UPDATE cache_entries SET recency = recency + 1 WHERE key = ?",
            (key,),
        )
        await db.commit()
        entry = _row_to_entry(row)
        entry.recency += 1
        return entry

    async def set(
        self, key: str, value: CacheEntry, ttl: int | None = None
    ) -> None:
        db = await self._conn()
        effective_ttl = ttl if ttl is not None else value.ttl
        expires_at: str | None = None
        if effective_ttl is not None:
            expires_at = _dt_to_iso(
                datetime.utcnow() + timedelta(seconds=effective_ttl)
            )
        await db.execute(
            """
            INSERT INTO cache_entries (
                key, content, ttl, recency, confidence, tags, source,
                created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                content = excluded.content,
                ttl = excluded.ttl,
                recency = excluded.recency,
                confidence = excluded.confidence,
                tags = excluded.tags,
                source = excluded.source,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (
                key,
                value.content,
                effective_ttl,
                value.recency,
                value.confidence,
                json.dumps(value.tags),
                value.source,
                _dt_to_iso(value.created_at),
                expires_at,
            ),
        )
        await db.commit()

    async def delete(self, key: str) -> None:
        db = await self._conn()
        await db.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
        await db.commit()

    async def search_by_tags(
        self, tags: list[str], limit: int = 20
    ) -> list[CacheEntry]:
        if not tags:
            return []
        db = await self._conn()
        await self._purge_expired(db)
        placeholders = ", ".join("?" for _ in tags)
        cursor = await db.execute(
            f"""
            SELECT * FROM cache_entries
            WHERE EXISTS (
                SELECT 1 FROM json_each(cache_entries.tags)
                WHERE json_each.value IN ({placeholders})
            )
            ORDER BY recency DESC, created_at DESC
            LIMIT ?
            """,
            (*tags, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_entry(row) for row in rows]

    async def search_by_query(
        self, query: str, limit: int = 20
    ) -> list[CacheEntry]:
        db = await self._conn()
        await self._purge_expired(db)
        pattern = f"%{query}%"
        cursor = await db.execute(
            """
            SELECT * FROM cache_entries
            WHERE content LIKE ?
            ORDER BY recency DESC, created_at DESC
            LIMIT ?
            """,
            (pattern, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_entry(row) for row in rows]

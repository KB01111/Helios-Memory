"""SQLite implementation of Mnemosyne episodic memory."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import aiosqlite

from helios_memory.models.storage import (
    ConflictResolution,
    Episode,
    MemoryEvent,
)
from helios_memory.providers.sqlite._db import connect

TIER = "mnemosyne"


def _dt_to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _iso_to_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _row_to_episode(row: aiosqlite.Row) -> Episode:
    metadata: dict = {}
    raw_tags = row["tags"]
    if raw_tags:
        try:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, dict):
                metadata = parsed
            elif isinstance(parsed, list):
                metadata = {"tags": parsed}
        except json.JSONDecodeError:
            metadata = {"tags_raw": raw_tags}
    return Episode(
        id=row["id"],
        content=row["content"],
        episode_type=row["memory_type"],
        confidence=row["confidence"] * row["decay_factor"],
        created_at=_iso_to_dt(row["created_at"]) or datetime.utcnow(),
        corrected_at=_iso_to_dt(row["updated_at"])
        if row["updated_at"] != row["created_at"]
        else None,
        metadata=metadata,
    )


class SQLiteEpisodicStore:
    """Mnemosyne tier — episodic memories with confidence, decay, and conflicts."""

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

    async def store_episode(self, episode: Episode) -> str:
        db = await self._conn()
        memory_id = episode.id if episode.id else str(uuid.uuid4())
        now = _dt_to_iso(datetime.utcnow())
        tags_payload = json.dumps(episode.metadata or {})
        await db.execute(
            """
            INSERT INTO memories (
                id, tier, content, memory_type, confidence, tags, source,
                created_at, updated_at, decay_factor, superseded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, NULL)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                memory_type = excluded.memory_type,
                confidence = excluded.confidence,
                tags = excluded.tags,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                memory_id,
                TIER,
                episode.content,
                episode.episode_type,
                episode.confidence,
                tags_payload,
                episode.metadata.get("source"),
                _dt_to_iso(episode.created_at),
                now,
            ),
        )
        await db.commit()
        return memory_id

    async def retrieve_relevant(
        self, query: str, limit: int = 10
    ) -> list[Episode]:
        db = await self._conn()
        pattern = f"%{query}%"
        cursor = await db.execute(
            """
            SELECT * FROM memories
            WHERE tier = ? AND superseded_by IS NULL
              AND (content LIKE ? OR tags LIKE ? OR memory_type LIKE ?)
            ORDER BY confidence * decay_factor DESC, created_at DESC
            LIMIT ?
            """,
            (TIER, pattern, pattern, pattern, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_episode(row) for row in rows]

    async def get_episode(self, memory_id: str) -> Episode | None:
        db = await self._conn()
        cursor = await db.execute(
            """
            SELECT * FROM memories
            WHERE id = ? AND tier = ?
            """,
            (memory_id, TIER),
        )
        row = await cursor.fetchone()
        return _row_to_episode(row) if row else None

    async def update_confidence(self, memory_id: str, delta: float) -> None:
        db = await self._conn()
        now = _dt_to_iso(datetime.utcnow())
        await db.execute(
            """
            UPDATE memories
            SET confidence = MAX(0.0, MIN(1.0, confidence + ?)),
                updated_at = ?
            WHERE id = ? AND tier = ?
            """,
            (delta, now, memory_id, TIER),
        )
        await db.commit()

    async def resolve_conflict(
        self, memory_id: str, resolution: ConflictResolution
    ) -> None:
        db = await self._conn()
        now = _dt_to_iso(datetime.utcnow())
        loser_id = resolution.losing_memory_id or memory_id
        await db.execute(
            """
            UPDATE memories
            SET superseded_by = ?, updated_at = ?
            WHERE id = ? AND tier = ?
            """,
            (resolution.winning_memory_id, now, loser_id, TIER),
        )
        await db.execute(
            """
            UPDATE conflicts
            SET status = 'resolved', resolution = ?, resolved_at = ?
            WHERE (memory_id_a = ? AND memory_id_b = ?)
               OR (memory_id_a = ? AND memory_id_b = ?)
            """,
            (
                resolution.reason,
                now,
                resolution.winning_memory_id,
                loser_id,
                loser_id,
                resolution.winning_memory_id,
            ),
        )
        await db.commit()

    async def apply_decay(self, as_of: datetime) -> int:
        db = await self._conn()
        as_of_iso = _dt_to_iso(as_of)
        cursor = await db.execute(
            """
            UPDATE memories
            SET decay_factor = decay_factor * 0.99,
                updated_at = ?
            WHERE tier = ?
              AND superseded_by IS NULL
              AND created_at < ?
            """,
            (as_of_iso, TIER, as_of_iso),
        )
        await db.commit()
        return cursor.rowcount

    async def append_audit_event(self, event: MemoryEvent) -> None:
        db = await self._conn()
        event_id = event.id or str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO memory_events (
                id, memory_id, event_type, payload, actor, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.memory_id,
                event.event_type,
                json.dumps(event.payload),
                event.actor,
                _dt_to_iso(event.created_at),
            ),
        )
        await db.commit()

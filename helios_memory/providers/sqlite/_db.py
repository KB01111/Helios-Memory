"""Shared SQLite connection and schema helpers."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


async def connect(db_path: str) -> aiosqlite.Connection:
    """Open a connection and apply idempotent schema initialization."""
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await init_schema(db)
    return db


async def init_schema(db: aiosqlite.Connection) -> None:
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    await db.executescript(schema_sql)
    await db.commit()

"""SQLite implementation of OpenViking semantic archive."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import aiosqlite

from helios_memory.models import TieredRetrieval
from helios_memory.models.storage import Document, DocumentChunk
from helios_memory.providers.sqlite._db import connect


def _dt_to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _iso_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _serialize_embedding(
    embedding: bytes | list[float] | None,
) -> bytes | None:
    if embedding is None:
        return None
    if isinstance(embedding, bytes):
        return embedding
    return json.dumps(embedding).encode("utf-8")


def _deserialize_embedding(raw: bytes | None) -> bytes | None:
    if raw is None:
        return None
    return raw


def _row_to_chunk(row: aiosqlite.Row) -> DocumentChunk:
    return DocumentChunk(
        id=row["id"],
        document_id=row["document_id"],
        level=row["level"],
        content=row["content"],
        embedding=_deserialize_embedding(row["embedding"]),
        metadata=json.loads(row["metadata"]),
        created_at=_iso_to_dt(row["created_at"]),
    )


class SQLiteVectorArchive:
    """OpenViking tier — tiered document chunks (L0/L1/L2)."""

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

    async def ingest_document(
        self, doc: Document, chunks: list[DocumentChunk]
    ) -> str:
        db = await self._conn()
        document_id = doc.id or str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO documents (id, title, source, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                source = excluded.source,
                metadata = excluded.metadata
            """,
            (
                document_id,
                doc.title,
                doc.source,
                json.dumps(doc.metadata),
                _dt_to_iso(doc.created_at),
            ),
        )
        for chunk in chunks:
            chunk_id = chunk.id or str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO document_chunks (
                    id, document_id, level, content, embedding, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    embedding = excluded.embedding,
                    metadata = excluded.metadata
                """,
                (
                    chunk_id,
                    document_id,
                    chunk.level,
                    chunk.content,
                    _serialize_embedding(chunk.embedding),
                    json.dumps(chunk.metadata),
                    _dt_to_iso(chunk.created_at),
                ),
            )
        await db.commit()
        return document_id

    async def retrieve_tiered(
        self, query: str, levels: list[int] | None = None
    ) -> TieredRetrieval:
        effective_levels = levels if levels is not None else [0, 1, 2]
        db = await self._conn()
        pattern = f"%{query}%"
        buckets: dict[int, list[dict[str, Any]]] = {0: [], 1: [], 2: []}
        for level in effective_levels:
            if level not in buckets:
                continue
            cursor = await db.execute(
                """
                SELECT * FROM document_chunks
                WHERE level = ? AND content LIKE ?
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (level, pattern),
            )
            rows = await cursor.fetchall()
            buckets[level] = [
                _row_to_chunk(row).model_dump(mode="json") for row in rows
            ]
        return TieredRetrieval(
            level_0=buckets[0],
            level_1=buckets[1],
            level_2=buckets[2],
        )

    async def search_metadata(
        self, filters: dict[str, Any]
    ) -> list[DocumentChunk]:
        db = await self._conn()
        clauses: list[str] = []
        params: list[Any] = []
        if "document_id" in filters:
            clauses.append("document_id = ?")
            params.append(filters["document_id"])
        if "level" in filters:
            clauses.append("level = ?")
            params.append(filters["level"])
        for key, value in filters.items():
            if key in ("document_id", "level"):
                continue
            clauses.append("json_extract(metadata, ?) = ?")
            params.extend([f"$.{key}", value])
        where = " AND ".join(clauses) if clauses else "1=1"
        cursor = await db.execute(
            f"SELECT * FROM document_chunks WHERE {where} ORDER BY created_at DESC",
            params,
        )
        rows = await cursor.fetchall()
        return [_row_to_chunk(row) for row in rows]

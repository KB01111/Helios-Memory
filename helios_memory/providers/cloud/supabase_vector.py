"""Supabase pgvector OpenViking archive (MVP stub)."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from helios_memory.models import TieredRetrieval
from helios_memory.models.storage import Document, DocumentChunk

logger = logging.getLogger(__name__)


def _stub(method: str) -> None:
    logger.warning("SupabaseVectorArchive.%s is not implemented (MVP stub)", method)


class SupabaseVectorArchive:
    """Semantic archive backed by Supabase pgvector.

    Activation:
        Set ``SUPABASE_URL``, ``SUPABASE_KEY``, and ``SUPABASE_DB_URL``.

    MVP:
        Connection check on ``connect()``; ingest/retrieve return empty results.
    """

    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        db_url: str | None = None,
    ) -> None:
        self._url = url or os.environ.get("SUPABASE_URL", "")
        self._key = key or os.environ.get("SUPABASE_KEY", "")
        self._db_url = db_url or os.environ.get("SUPABASE_DB_URL", "")
        self._connected = False

    async def connect(self) -> None:
        """Verify required Supabase environment variables are present."""
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", self._url),
                ("SUPABASE_KEY", self._key),
                ("SUPABASE_DB_URL", self._db_url),
            )
            if not value
        ]
        if missing:
            logger.warning(
                "SupabaseVectorArchive: missing env vars %s; operating in stub mode",
                ", ".join(missing),
            )
        else:
            logger.info("SupabaseVectorArchive: credentials configured (MVP stub)")
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def ingest_document(
        self,
        doc: Document,
        chunks: list[DocumentChunk],
    ) -> str:
        _stub("ingest_document")
        return doc.id or str(uuid.uuid4())

    async def retrieve_tiered(
        self,
        query: str,
        levels: list[int] | None = None,
    ) -> TieredRetrieval:
        _stub("retrieve_tiered")
        return TieredRetrieval()

    async def search_metadata(
        self,
        filters: dict[str, Any],
    ) -> list[DocumentChunk]:
        _stub("search_metadata")
        return []

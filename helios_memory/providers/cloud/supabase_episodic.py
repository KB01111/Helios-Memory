"""Supabase-backed Mnemosyne episodic memory store (MVP stub)."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from helios_memory.models.storage import ConflictResolution, Episode, MemoryEvent

logger = logging.getLogger(__name__)


def _stub(method: str) -> None:
    logger.warning("SupabaseEpisodicStore.%s is not implemented (MVP stub)", method)


class SupabaseEpisodicStore:
    """Postgres-backed episodic memory via Supabase.

    Maps to ``memories`` and ``memory_events`` tables.

    Activation:
        Set ``SUPABASE_URL``, ``SUPABASE_KEY``, and ``SUPABASE_DB_URL``.

    MVP:
        Performs a connection check on ``connect()``; all mutation/query
        methods log a warning and return empty or no-op results.
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
                "SupabaseEpisodicStore: missing env vars %s; operating in stub mode",
                ", ".join(missing),
            )
        else:
            logger.info("SupabaseEpisodicStore: credentials configured (MVP stub)")
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def store_episode(self, episode: Episode) -> str:
        _stub("store_episode")
        return episode.id or str(uuid.uuid4())

    async def retrieve_relevant(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Episode]:
        _stub("retrieve_relevant")
        return []

    async def get_episode(self, memory_id: str) -> Episode | None:
        _stub("get_episode")
        return None

    async def update_confidence(self, memory_id: str, delta: float) -> None:
        _stub("update_confidence")

    async def resolve_conflict(
        self,
        memory_id: str,
        resolution: ConflictResolution,
    ) -> None:
        _stub("resolve_conflict")

    async def apply_decay(self, as_of: datetime) -> int:
        _stub("apply_decay")
        return 0

    async def append_audit_event(self, event: MemoryEvent) -> None:
        _stub("append_audit_event")

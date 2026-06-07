"""Postgres episodic memory store — non-Supabase (MVP stub)."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from helios_memory.models.storage import ConflictResolution, Episode, MemoryEvent

logger = logging.getLogger(__name__)


def _stub(method: str) -> None:
    logger.warning("PostgresEpisodicStore.%s is not implemented (MVP stub)", method)


class PostgresEpisodicStore:
    """Episodic memory backed by a generic Postgres database.

    Activation:
        Set ``DATABASE_URL`` (e.g. ``postgresql://user:pass@host/db``).

    MVP:
        Schema mirrors SQLite episodic tables where possible; methods are stubbed
        until a full async driver integration is added.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL", "")
        self._connected = False

    async def connect(self) -> None:
        """Verify DATABASE_URL is configured."""
        if not self._database_url:
            logger.warning(
                "PostgresEpisodicStore: DATABASE_URL not set; operating in stub mode"
            )
        else:
            logger.info("PostgresEpisodicStore: DATABASE_URL configured (MVP stub)")
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

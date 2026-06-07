"""Mnemosyne episodic memory store protocol."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from helios_memory.models.storage import (
        ConflictResolution,
        Episode,
        MemoryEvent,
    )


class EpisodicMemoryStore(Protocol):
    """Long-term episodic memory with confidence, decay, and conflict resolution."""

    async def store_episode(self, episode: Episode) -> str: ...

    async def retrieve_relevant(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Episode]: ...

    async def get_episode(self, memory_id: str) -> Episode | None: ...

    async def update_confidence(self, memory_id: str, delta: float) -> None: ...

    async def resolve_conflict(
        self,
        memory_id: str,
        resolution: ConflictResolution,
    ) -> None: ...

    async def apply_decay(self, as_of: datetime) -> int: ...

    async def append_audit_event(self, event: MemoryEvent) -> None: ...

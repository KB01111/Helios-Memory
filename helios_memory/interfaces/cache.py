"""Holographic cache store protocol (short-term memory tier)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from helios_memory.models.storage import CacheEntry


class CacheStore(Protocol):
    """Short-term holographic cache with TTL and tag search."""

    async def get(self, key: str) -> CacheEntry | None: ...

    async def set(
        self,
        key: str,
        value: CacheEntry,
        ttl: int | None = None,
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def search_by_tags(
        self,
        tags: list[str],
        limit: int = 20,
    ) -> list[CacheEntry]: ...

    async def search_by_query(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Any]:
        """Optional query-based retrieval; implementations may fall back to tags."""
        ...

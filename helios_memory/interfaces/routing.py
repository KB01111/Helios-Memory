"""Intent routing and memory synthesis protocols."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from helios_memory.models import Intent, MemoryBrief, TieredRetrieval

if TYPE_CHECKING:
    from helios_memory.models.storage import CacheEntry, Episode


class IntentRouter(Protocol):
    """Classifies user prompts into intent categories."""

    async def classify(self, prompt: str) -> Intent: ...


class MemorySynthesizer(Protocol):
    """Combines retrieved context into a compact memory brief."""

    async def synthesize(
        self,
        prompt: str,
        cache: list[CacheEntry],
        episodes: list[Episode],
        archive: TieredRetrieval,
    ) -> MemoryBrief: ...

"""End-to-end memory pipeline orchestration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from helios_memory.config import HeliosConfig
from helios_memory.models import IntentCategory, MemoryBrief, TieredRetrieval
from helios_memory.privacy import PrivacyEnforcer

if TYPE_CHECKING:
    from helios_memory.interfaces import (
        CacheStore,
        ConsolidationWorker,
        EpisodicMemoryStore,
        IntentRouter,
        MemorySynthesizer,
        ReasoningModel,
        VectorArchive,
    )
    from helios_memory.models.storage import CacheEntry, Episode

logger = logging.getLogger(__name__)

_EMPTY_BRIEF = MemoryBrief(summary="")


class MemoryWorkflow:
    """Orchestrates prompt → router → retrieve → synthesize → reason → consolidate."""

    def __init__(
        self,
        config: HeliosConfig,
        cache_store: CacheStore,
        episodic_store: EpisodicMemoryStore,
        vector_archive: VectorArchive,
        intent_router: IntentRouter,
        synthesizer: MemorySynthesizer,
        reasoning_model: ReasoningModel,
        consolidation_worker: ConsolidationWorker,
        privacy: PrivacyEnforcer | None = None,
    ) -> None:
        self.config = config
        self.cache_store = cache_store
        self.episodic_store = episodic_store
        self.vector_archive = vector_archive
        self.intent_router = intent_router
        self.synthesizer = synthesizer
        self.reasoning_model = reasoning_model
        self.consolidation_worker = consolidation_worker
        self.privacy = privacy or PrivacyEnforcer(config.privacy)

    async def run(self, user_prompt: str, session_id: str) -> str:
        """Execute the full memory-augmented response pipeline."""
        intent = await self.intent_router.classify(user_prompt)

        cache_hits: list[CacheEntry] = []
        episodes: list[Episode] = []
        archive = TieredRetrieval()

        if intent.requires_memory or intent.category == IntentCategory.MEMORY_LOOKUP_NEEDED:
            cache_hits = await self._retrieve_cache(user_prompt)
            episodes = await self.episodic_store.retrieve_relevant(user_prompt)

        if intent.requires_archive or intent.category == IntentCategory.PROJECT_CONTEXT_NEEDED:
            archive = await self.vector_archive.retrieve_tiered(user_prompt)

        brief = await self._build_brief(user_prompt, cache_hits, episodes, archive, intent)

        if self.config.is_cloud:
            decision = self.privacy.enforce_before_cloud(user_prompt)
            if not decision.allowed:
                if intent.category == IntentCategory.SENSITIVE_REQUEST:
                    return (
                        "I cannot process this request through cloud providers "
                        f"due to privacy policy: {decision.blocked_reason}"
                    )
                brief = MemoryBrief(
                    summary=decision.content if decision.content else brief.summary,
                    metadata={**brief.metadata, "privacy_redacted": True},
                )

        response = await self.reasoning_model.generate(
            user_prompt,
            brief,
            session_id,
        )

        if self.config.consolidation_enabled:
            self._schedule_consolidation(session_id, user_prompt, response, intent)

        return response

    async def _retrieve_cache(self, query: str) -> list[CacheEntry]:
        """Retrieve holographic cache hits, preferring query search when available."""
        if hasattr(self.cache_store, "search_by_query"):
            return await self.cache_store.search_by_query(query)
        return await self.cache_store.search_by_tags(_extract_tags(query))

    async def _build_brief(
        self,
        user_prompt: str,
        cache_hits: list[CacheEntry],
        episodes: list[Episode],
        archive: TieredRetrieval,
        intent: object,
    ) -> MemoryBrief:
        """Synthesize memory brief or return empty brief when retrieval is skipped."""
        needs_context = (
            cache_hits
            or episodes
            or archive.total_chunks > 0
            or getattr(intent, "requires_memory", False)
            or getattr(intent, "requires_archive", False)
        )
        if not needs_context:
            return _EMPTY_BRIEF

        return await self.synthesizer.synthesize(
            user_prompt,
            cache_hits,
            episodes,
            archive,
        )

    def _schedule_consolidation(
        self,
        session_id: str,
        user_prompt: str,
        response: str,
        intent: object,
    ) -> None:
        """Fire consolidation asynchronously without blocking the user response."""
        task = asyncio.create_task(
            self.consolidation_worker.consolidate(
                session_id,
                user_prompt,
                response,
                intent,  # type: ignore[arg-type]
            ),
            name=f"helios-consolidate-{session_id}",
        )
        task.add_done_callback(_log_consolidation_result)


def _extract_tags(query: str) -> list[str]:
    """Derive simple tags from a query for cache tag search."""
    words = [word.strip(".,!?\"'").lower() for word in query.split()]
    return [word for word in words if len(word) > 3][:5]


def _log_consolidation_result(task: asyncio.Task[object]) -> None:
    """Log consolidation failures without surfacing to the user."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception("Consolidation failed", exc_info=exc)

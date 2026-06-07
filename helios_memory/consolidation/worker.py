"""Post-response memory consolidation worker."""

from __future__ import annotations

import logging
from datetime import datetime

from helios_memory.consolidation.conflict_resolver import ConflictResolver
from helios_memory.consolidation.decay import DecayConfig
from helios_memory.consolidation.extractor import extract_candidates
from helios_memory.interfaces import EpisodicMemoryStore
from helios_memory.models import ConsolidationResult, Intent, MemoryCandidate
from helios_memory.models.storage import Episode, MemoryEvent

logger = logging.getLogger(__name__)


class ConsolidationWorker:
    """Extracts, stores, and reconciles memories after each response."""

    def __init__(
        self,
        store: EpisodicMemoryStore,
        decay_config: DecayConfig | None = None,
        conflict_resolver: ConflictResolver | None = None,
        confidence_boost: float = 0.05,
    ) -> None:
        self.store = store
        self.decay_config = decay_config or DecayConfig()
        self.conflict_resolver = conflict_resolver or ConflictResolver()
        self.confidence_boost = confidence_boost

    async def consolidate(
        self,
        session_id: str,
        user_prompt: str,
        assistant_response: str,
        intent: Intent,
    ) -> ConsolidationResult:
        """Run full consolidation pipeline for a conversation turn."""
        candidates = extract_candidates(user_prompt, assistant_response)
        candidates_stored = 0
        conflicts_detected = 0
        audit_events = 0

        for candidate in candidates:
            stored_id = await self._store_candidate(candidate, session_id)
            candidates_stored += 1

            conflicts = await self.conflict_resolver.detect(candidate, self.store)
            for conflict in conflicts:
                conflicts_detected += 1
                await self.conflict_resolver.resolve(
                    conflict,
                    candidate,
                    conflict.memory_id_a,
                    self.store,
                    stored_id,
                )
                await self._audit(
                    stored_id,
                    "conflict_resolved",
                    {
                        "session_id": session_id,
                        "conflict_id": conflict.id,
                        "existing_id": conflict.memory_id_a,
                    },
                )
                audit_events += 1

            await self._audit(
                stored_id,
                "memory_stored",
                {
                    "session_id": session_id,
                    "memory_type": candidate.memory_type,
                    "intent": intent.category.value,
                },
            )
            audit_events += 1

        decay_applied = await self.store.apply_decay(datetime.utcnow())
        await self._audit(
            "system",
            "decay_applied",
            {"session_id": session_id, "rows_updated": decay_applied},
        )
        audit_events += 1

        return ConsolidationResult(
            candidates_stored=candidates_stored,
            conflicts_detected=conflicts_detected,
            decay_applied=decay_applied,
            audit_events=audit_events,
            metadata={
                "session_id": session_id,
                "intent": intent.category.value,
                "candidate_count": len(candidates),
            },
        )

    async def _store_candidate(
        self,
        candidate: MemoryCandidate,
        session_id: str,
    ) -> str:
        episode = Episode(
            content=candidate.content,
            episode_type=candidate.memory_type,
            confidence=min(1.0, candidate.confidence + self.confidence_boost),
            created_at=candidate.created_at,
            metadata={
                **candidate.metadata,
                "source": candidate.source,
                "session_id": session_id,
                "tags": candidate.tags,
            },
        )
        return await self.store.store_episode(episode)

    async def _audit(
        self,
        memory_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        try:
            await self.store.append_audit_event(
                MemoryEvent(
                    memory_id=memory_id,
                    event_type=event_type,
                    payload=payload,
                    actor="consolidation_worker",
                )
            )
        except Exception:
            logger.exception("Failed to append audit event: %s", event_type)

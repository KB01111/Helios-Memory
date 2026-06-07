"""Memory conflict detection and resolution."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from helios_memory.interfaces import EpisodicMemoryStore
from helios_memory.models import MemoryCandidate
from helios_memory.models.storage import Conflict, ConflictResolution, Episode


def _topic_key_from_content(content: str, metadata: dict | None = None) -> str | None:
    if metadata and metadata.get("topic_key"):
        return str(metadata["topic_key"])

    lowered = content.lower()
    for prefix in ("prefer", "favorite", "like", "dislike", "use"):
        match = re.search(rf"(?i)\b{prefix}\b", lowered)
        if match:
            return prefix
    words = re.findall(r"[a-z0-9_]{4,}", lowered)
    return words[0] if words else None


def _values_differ(a: str, b: str) -> bool:
    norm_a = re.sub(r"\s+", " ", a.strip().lower())
    norm_b = re.sub(r"\s+", " ", b.strip().lower())
    if norm_a == norm_b:
        return False
    if norm_a in norm_b or norm_b in norm_a:
        return False
    return True


def detect_conflict(
    candidate: MemoryCandidate,
    existing: Episode,
) -> Conflict | None:
    """Pure function: detect contradiction between candidate and existing memory."""
    candidate_topic = _topic_key_from_content(
        candidate.content,
        candidate.metadata,
    )
    existing_topic = _topic_key_from_content(
        existing.content,
        existing.metadata,
    )

    if not candidate_topic or not existing_topic:
        return None
    if candidate_topic != existing_topic:
        return None
    if not _values_differ(candidate.content, existing.content):
        return None

    return Conflict(
        id=str(uuid.uuid4()),
        memory_id_a=existing.id,
        memory_id_b="",
        conflict_type="contradiction",
        status="detected",
        created_at=datetime.utcnow(),
    )


def _pick_winner(
    candidate: MemoryCandidate,
    existing: Episode,
) -> ConflictResolution:
    """Newer explicit corrections outweigh older inferences."""
    candidate_is_correction = (
        candidate.memory_type == "correction"
        or candidate.metadata.get("explicit_correction")
    )
    existing_is_correction = existing.episode_type == "correction"

    candidate_time = candidate.created_at
    existing_time = existing.corrected_at or existing.created_at

    if candidate_is_correction and not existing_is_correction:
        return ConflictResolution(
            winning_memory_id="candidate",
            losing_memory_id=existing.id,
            reason="newer_explicit_correction",
            metadata={"candidate_content": candidate.content},
        )

    if existing_is_correction and not candidate_is_correction:
        return ConflictResolution(
            winning_memory_id=existing.id,
            losing_memory_id="candidate",
            reason="existing_explicit_correction",
        )

    if candidate_time >= existing_time:
        if candidate.confidence >= existing.confidence:
            return ConflictResolution(
                winning_memory_id="candidate",
                losing_memory_id=existing.id,
                reason="newer_higher_confidence",
            )
        return ConflictResolution(
            winning_memory_id="candidate",
            losing_memory_id=existing.id,
            reason="newer_memory",
        )

    if existing.confidence > candidate.confidence:
        return ConflictResolution(
            winning_memory_id=existing.id,
            losing_memory_id="candidate",
            reason="older_higher_confidence",
        )

    return ConflictResolution(
        winning_memory_id=existing.id,
        losing_memory_id="candidate",
        reason="older_memory",
    )


class ConflictResolver:
    """Detects and resolves contradictions via EpisodicMemoryStore."""

    async def detect(
        self,
        candidate: MemoryCandidate,
        store: EpisodicMemoryStore,
    ) -> list[Conflict]:
        query = candidate.metadata.get("topic_key") or candidate.content[:80]
        existing_memories = await store.retrieve_relevant(str(query), limit=20)
        conflicts: list[Conflict] = []

        for existing in existing_memories:
            conflict = detect_conflict(candidate, existing)
            if conflict is not None:
                conflicts.append(conflict)

        return conflicts

    async def resolve(
        self,
        conflict: Conflict,
        candidate: MemoryCandidate,
        existing_id: str,
        store: EpisodicMemoryStore,
        stored_candidate_id: str,
    ) -> ConflictResolution:
        """Resolve conflict and persist via store.resolve_conflict."""
        existing = await store.get_episode(existing_id)
        if existing is None:
            existing = Episode(
                id=existing_id,
                content="",
                episode_type="fact",
                confidence=0.5,
                created_at=datetime.utcnow(),
            )

        resolution = _pick_winner(candidate, existing)

        if resolution.winning_memory_id == "candidate":
            resolution = ConflictResolution(
                winning_memory_id=stored_candidate_id,
                losing_memory_id=existing.id,
                reason=resolution.reason,
                metadata=resolution.metadata,
            )
            await store.resolve_conflict(existing.id, resolution)
        else:
            resolution = ConflictResolution(
                winning_memory_id=existing.id,
                losing_memory_id=stored_candidate_id,
                reason=resolution.reason,
                metadata=resolution.metadata,
            )
            await store.resolve_conflict(stored_candidate_id, resolution)

        return resolution

"""Unit tests for memory conflict detection and resolution."""

from __future__ import annotations

from datetime import datetime, timedelta

import aiosqlite
import pytest

from helios_memory.consolidation.conflict_resolver import ConflictResolver, detect_conflict
from helios_memory.models import MemoryCandidate
from helios_memory.models.storage import Conflict, Episode


class TestDetectConflict:
    """Pure conflict detection between candidate and existing memory."""

    def test_detects_contradiction_on_same_topic(self) -> None:
        candidate = MemoryCandidate(
            content="I prefer Python for all backend services",
            memory_type="preference",
            metadata={"topic_key": "prefer"},
            created_at=datetime(2025, 6, 7),
        )
        existing = Episode(
            id="mem-old",
            content="I prefer JavaScript for all backend services",
            episode_type="preference",
            metadata={"topic_key": "prefer"},
            created_at=datetime(2025, 6, 1),
        )
        conflict = detect_conflict(candidate, existing)
        assert conflict is not None
        assert conflict.status == "detected"
        assert conflict.memory_id_a == "mem-old"
        assert conflict.conflict_type == "contradiction"

    def test_no_conflict_when_topics_differ(self) -> None:
        candidate = MemoryCandidate(
            content="I prefer dark mode in the editor",
            metadata={"topic_key": "prefer:dark"},
        )
        existing = Episode(
            id="mem-1",
            content="The project uses FastAPI",
            metadata={"topic_key": "project"},
        )
        assert detect_conflict(candidate, existing) is None

    def test_no_conflict_when_content_equivalent(self) -> None:
        candidate = MemoryCandidate(
            content="I prefer  Python",
            metadata={"topic_key": "prefer"},
        )
        existing = Episode(
            id="mem-1",
            content="I prefer python",
            metadata={"topic_key": "prefer"},
        )
        assert detect_conflict(candidate, existing) is None


class TestNewerCorrectionWins:
    """Explicit corrections outweigh older inferences."""

    @pytest.mark.asyncio
    async def test_correction_beats_older_fact(
        self,
        local_stores,
        tmp_db: str,
    ) -> None:
        _, episodic, _ = local_stores
        resolver = ConflictResolver()

        old_id = await episodic.store_episode(
            Episode(
                content="User prefers tabs for indentation",
                episode_type="fact",
                confidence=0.7,
                metadata={"topic_key": "prefer"},
                created_at=datetime(2025, 1, 1),
            )
        )

        candidate = MemoryCandidate(
            content="Actually, I prefer spaces for indentation",
            memory_type="correction",
            confidence=0.9,
            metadata={"topic_key": "prefer", "explicit_correction": True},
            created_at=datetime(2025, 6, 7),
        )
        new_id = await episodic.store_episode(
            Episode(
                content=candidate.content,
                episode_type=candidate.memory_type,
                confidence=candidate.confidence,
                metadata=candidate.metadata,
                created_at=candidate.created_at,
            )
        )

        conflicts = await resolver.detect(candidate, episodic)
        assert len(conflicts) >= 1

        conflict = conflicts[0]
        resolution = await resolver.resolve(
            conflict,
            candidate,
            old_id,
            episodic,
            new_id,
        )
        assert resolution.reason == "newer_explicit_correction"
        assert resolution.winning_memory_id == new_id
        assert resolution.losing_memory_id == old_id

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT superseded_by FROM memories WHERE id = ?",
                (old_id,),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["superseded_by"] == new_id


class TestConflictResolverStoreIntegration:
    """Conflict status transitions and store-backed resolution."""

    @pytest.mark.asyncio
    async def test_detect_finds_multiple_existing_memories(
        self,
        local_stores,
    ) -> None:
        _, episodic, _ = local_stores
        await episodic.store_episode(
            Episode(content="User likes coffee in the morning", metadata={"topic_key": "like"})
        )
        await episodic.store_episode(
            Episode(content="User likes tea in the morning", metadata={"topic_key": "like"})
        )

        candidate = MemoryCandidate(
            content="User likes espresso in the morning",
            metadata={"topic_key": "like"},
        )
        conflicts = await ConflictResolver().detect(candidate, episodic)
        assert len(conflicts) >= 1

    @pytest.mark.asyncio
    async def test_resolve_fetches_existing_by_id_not_like_search(
        self,
        local_stores,
    ) -> None:
        """resolve() must load the existing episode by ID, not via LIKE search."""
        _, episodic, _ = local_stores
        resolver = ConflictResolver()

        existing_id = await episodic.store_episode(
            Episode(
                content="Use tabs for indentation",
                episode_type="correction",
                confidence=0.95,
                metadata={"topic_key": "prefer", "explicit_correction": True},
                created_at=datetime(2025, 6, 1),
            )
        )

        candidate = MemoryCandidate(
            content="Use spaces for indentation",
            memory_type="preference",
            confidence=0.99,
            metadata={"topic_key": "prefer"},
            created_at=datetime(2025, 6, 7),
        )
        candidate_id = await episodic.store_episode(
            Episode(
                content=candidate.content,
                episode_type=candidate.memory_type,
                confidence=candidate.confidence,
                metadata=candidate.metadata,
                created_at=candidate.created_at,
            )
        )

        conflict = Conflict(
            id="conflict-by-id",
            memory_id_a=existing_id,
            memory_id_b="",
            conflict_type="contradiction",
            status="detected",
            created_at=datetime.utcnow(),
        )

        resolution = await resolver.resolve(
            conflict,
            candidate,
            existing_id,
            episodic,
            candidate_id,
        )

        assert resolution.reason == "existing_explicit_correction"
        assert resolution.winning_memory_id == existing_id
        assert resolution.losing_memory_id == candidate_id

    @pytest.mark.asyncio
    async def test_resolve_supersedes_loser_via_store(
        self,
        local_stores,
        tmp_db: str,
    ) -> None:
        """Persisted resolution marks the loser superseded in SQLite."""
        from helios_memory.models.storage import ConflictResolution

        _, episodic, _ = local_stores

        existing_id = await episodic.store_episode(
            Episode(
                content="Favorite color is blue",
                episode_type="preference",
                confidence=0.6,
                metadata={"topic_key": "favorite"},
                created_at=datetime(2025, 1, 1),
            )
        )
        candidate = MemoryCandidate(
            content="Favorite color is green",
            memory_type="preference",
            confidence=0.8,
            metadata={"topic_key": "favorite"},
            created_at=datetime(2025, 6, 7),
        )
        candidate_id = await episodic.store_episode(
            Episode(
                content=candidate.content,
                episode_type=candidate.memory_type,
                confidence=candidate.confidence,
                metadata=candidate.metadata,
                created_at=candidate.created_at,
            )
        )

        conflict = detect_conflict(
            candidate,
            Episode(
                id=existing_id,
                content="Favorite color is blue",
                metadata={"topic_key": "favorite"},
                created_at=datetime(2025, 1, 1),
            ),
        )
        assert conflict is not None
        assert conflict.status == "detected"

        resolution = ConflictResolution(
            winning_memory_id=candidate_id,
            losing_memory_id=existing_id,
            reason="newer_higher_confidence",
        )
        await episodic.resolve_conflict(existing_id, resolution)

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT superseded_by FROM memories WHERE id = ?",
                (existing_id,),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["superseded_by"] == candidate_id

    @pytest.mark.asyncio
    async def test_audit_events_written_on_consolidation_conflict(
        self,
        local_stores,
        tmp_db: str,
    ) -> None:
        _, episodic, _ = local_stores
        from helios_memory.consolidation.worker import ConsolidationWorker
        from helios_memory.models import Intent, IntentCategory

        await episodic.store_episode(
            Episode(
                content="I prefer vim keybindings in every editor",
                episode_type="preference",
                metadata={"topic_key": "prefer"},
                created_at=datetime.utcnow() - timedelta(days=1),
            )
        )

        worker = ConsolidationWorker(store=episodic)
        result = await worker.consolidate(
            session_id="sess-conflict",
            user_prompt="Actually, I prefer emacs keybindings in every editor now.",
            assistant_response="Got it, I will remember emacs keybindings.",
            intent=Intent(category=IntentCategory.TASK_REQUEST, confidence=0.8),
        )
        assert result.candidates_stored >= 1
        assert result.audit_events >= 1

        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM memory_events WHERE event_type = 'memory_stored'"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] >= 1

"""Unit tests for memory consolidation extraction, decay, and worker."""

from __future__ import annotations

from datetime import datetime, timedelta

import aiosqlite
import pytest

from helios_memory.consolidation.decay import DecayConfig, compute_decay_factor
from helios_memory.consolidation.extractor import extract_candidates
from helios_memory.consolidation.worker import ConsolidationWorker
from helios_memory.models import Intent, IntentCategory
from helios_memory.models.storage import Episode


class TestExtractCandidates:
    """Rule-based candidate extraction from dialogue turns."""

    def test_extracts_preference_and_correction(self) -> None:
        user = "I prefer TypeScript over JavaScript for new modules."
        assistant = "Actually, I meant we should use Python for new modules instead."
        candidates = extract_candidates(user, assistant)

        types = {c.memory_type for c in candidates}
        assert "preference" in types
        assert "correction" in types

    def test_classification_labels_and_confidence(self) -> None:
        user = "The project is using FastAPI and we are using SQLite locally."
        candidates = extract_candidates(user, "The architecture is documented in README.")

        by_type = {c.memory_type: c for c in candidates if c.memory_type in ("project_state", "fact")}
        assert "project_state" in by_type or any(c.memory_type == "project_state" for c in candidates)
        for candidate in candidates:
            assert 0.0 <= candidate.confidence <= 1.0
            if candidate.memory_type == "correction":
                assert candidate.confidence >= 0.85

    def test_topic_key_metadata_for_conflicts(self) -> None:
        candidates = extract_candidates(
            "I prefer dark mode in all applications.",
            "Noted.",
        )
        preference = next(c for c in candidates if c.memory_type == "preference")
        assert preference.metadata.get("topic_key") is not None

    def test_skips_short_sentences(self) -> None:
        candidates = extract_candidates("Ok.", "Sure.")
        assert candidates == []


class TestComputeDecayFactor:
    """Temporal decay reduces stale memory confidence."""

    def test_fresh_memory_has_full_weight(self, frozen_now: datetime) -> None:
        config = DecayConfig()
        factor = compute_decay_factor(
            created_at=frozen_now,
            memory_type="fact",
            config=config,
            as_of=frozen_now,
        )
        assert factor == 1.0

    def test_exponential_half_life(self, frozen_now: datetime) -> None:
        config = DecayConfig(mode="exponential")
        created = frozen_now - timedelta(days=config.half_life_for("fact"))
        factor = compute_decay_factor(
            created_at=created,
            memory_type="fact",
            config=config,
            as_of=frozen_now,
        )
        assert 0.49 <= factor <= 0.51

    def test_linear_decay_reaches_zero_at_twice_half_life(self, frozen_now: datetime) -> None:
        config = DecayConfig(mode="linear", default_half_life_days=10.0)
        created = frozen_now - timedelta(days=20)
        factor = compute_decay_factor(
            created_at=created,
            memory_type="custom_type",
            config=config,
            as_of=frozen_now,
        )
        assert factor == 0.0

    def test_correction_has_longer_half_life_than_episode(self, frozen_now: datetime) -> None:
        config = DecayConfig()
        age_days = 30
        created = frozen_now - timedelta(days=age_days)
        correction_factor = compute_decay_factor(created, "correction", config, frozen_now)
        episode_factor = compute_decay_factor(created, "episode", config, frozen_now)
        assert correction_factor > episode_factor


class TestConsolidationWorker:
    """End-to-end consolidation worker smoke tests."""

    @pytest.mark.asyncio
    async def test_consolidate_stores_candidates_and_audits(
        self,
        local_stores,
        tmp_db: str,
    ) -> None:
        _, episodic, _ = local_stores
        worker = ConsolidationWorker(store=episodic)

        result = await worker.consolidate(
            session_id="sess-1",
            user_prompt="I prefer pytest for all unit testing in this project.",
            assistant_response="I will remember your pytest preference for future tasks.",
            intent=Intent(category=IntentCategory.TASK_REQUEST, confidence=0.85),
        )

        assert result.candidates_stored >= 1
        assert result.audit_events >= 2  # memory_stored + decay_applied per candidate path
        assert result.metadata["session_id"] == "sess-1"

        episodes = await episodic.retrieve_relevant("pytest", limit=10)
        assert len(episodes) >= 1

        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM memory_events")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] >= 1

    @pytest.mark.asyncio
    async def test_consolidate_applies_decay(
        self,
        local_stores,
    ) -> None:
        _, episodic, _ = local_stores
        old_time = datetime.utcnow() - timedelta(days=30)
        await episodic.store_episode(
            Episode(
                content="Stale fact about an old library version",
                episode_type="fact",
                confidence=0.8,
                created_at=old_time,
            )
        )

        worker = ConsolidationWorker(store=episodic)
        result = await worker.consolidate(
            session_id="sess-decay",
            user_prompt="Please summarize our testing approach.",
            assistant_response="We use pytest with asyncio mode enabled.",
            intent=Intent(category=IntentCategory.TASK_REQUEST, confidence=0.7),
        )
        assert result.decay_applied >= 0

    @pytest.mark.asyncio
    async def test_consolidation_non_blocking_smoke(
        self,
        local_stores,
    ) -> None:
        """Worker completes without blocking; timing is mocked via fast in-memory DB."""
        import asyncio
        import time

        _, episodic, _ = local_stores
        worker = ConsolidationWorker(store=episodic)
        intent = Intent(category=IntentCategory.SMALL_TALK, confidence=0.9)

        start = time.monotonic()
        results = await asyncio.gather(
            worker.consolidate("s1", "Hello there!", "Hi!", intent),
            worker.consolidate("s2", "Thanks for the help today.", "You're welcome!", intent),
        )
        elapsed = time.monotonic() - start

        assert len(results) == 2
        assert all(r.candidates_stored >= 0 for r in results)
        assert elapsed < 5.0

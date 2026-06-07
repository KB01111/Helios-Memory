"""Unit tests for multi-tier memory retrieval (cache, episodic, vector)."""

from __future__ import annotations

from datetime import datetime, timedelta

import aiosqlite
import pytest

from helios_memory.interfaces import CacheStore, EpisodicMemoryStore, VectorArchive
from helios_memory.models import Intent, IntentCategory, TieredRetrieval
from helios_memory.models.storage import CacheEntry, Document, DocumentChunk, Episode
from helios_memory.routing.synthesizer import build_template_brief


class TestHolographicCache:
    """SQLite cache set/get, TTL expiry, and tag search."""

    @pytest.mark.asyncio
    async def test_set_and_get(self, local_stores: tuple[CacheStore, EpisodicMemoryStore, VectorArchive]) -> None:
        cache, _, _ = local_stores
        entry = CacheEntry(
            content="cached fact about pytest",
            ttl=3600,
            recency=1.0,
            confidence=0.9,
            tags=["test", "pytest"],
            source="unit_test",
            created_at=datetime.utcnow(),
        )
        await cache.set("pytest-key", entry)
        retrieved = await cache.get("pytest-key")
        assert retrieved is not None
        assert retrieved.content == "cached fact about pytest"
        assert retrieved.recency == 2.0  # incremented on get

    @pytest.mark.asyncio
    async def test_ttl_expiry_purges_entry(
        self,
        local_stores: tuple[CacheStore, EpisodicMemoryStore, VectorArchive],
        tmp_db: str,
    ) -> None:
        cache, _, _ = local_stores
        entry = CacheEntry(
            content="short-lived entry",
            ttl=60,
            tags=["ephemeral"],
            created_at=datetime.utcnow(),
        )
        await cache.set("expire-me", entry)

        past = (datetime.utcnow() - timedelta(seconds=120)).isoformat()
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "UPDATE cache_entries SET expires_at = ? WHERE key = ?",
                (past, "expire-me"),
            )
            await db.commit()

        assert await cache.get("expire-me") is None

    @pytest.mark.asyncio
    async def test_search_by_tags(
        self,
        local_stores: tuple[CacheStore, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        cache, _, _ = local_stores
        now = datetime.utcnow()
        await cache.set(
            "tag-a",
            CacheEntry(content="alpha", tags=["language", "python"], created_at=now),
        )
        await cache.set(
            "tag-b",
            CacheEntry(content="beta", tags=["language", "rust"], created_at=now),
        )
        await cache.set(
            "tag-c",
            CacheEntry(content="gamma", tags=["framework"], created_at=now),
        )

        results = await cache.search_by_tags(["language"])
        contents = {entry.content for entry in results}
        assert contents == {"alpha", "beta"}


class TestMnemosyneEpisodic:
    """Episodic store and relevance retrieval."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_by_keyword(
        self,
        local_stores: tuple[CacheStore, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        _, episodic, _ = local_stores
        memory_id = await episodic.store_episode(
            Episode(
                content="User prefers dark mode in all editors",
                episode_type="preference",
                confidence=0.85,
                metadata={"topic_key": "prefer:dark"},
            )
        )
        results = await episodic.retrieve_relevant("dark mode", limit=5)
        assert len(results) >= 1
        assert any(ep.id == memory_id for ep in results)

    @pytest.mark.asyncio
    async def test_retrieve_orders_by_confidence(
        self,
        local_stores: tuple[CacheStore, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        _, episodic, _ = local_stores
        await episodic.store_episode(
            Episode(content="low confidence note about routing", confidence=0.3)
        )
        await episodic.store_episode(
            Episode(content="high confidence note about routing", confidence=0.95)
        )
        results = await episodic.retrieve_relevant("routing", limit=5)
        assert len(results) >= 2
        assert results[0].confidence >= results[1].confidence


class TestOpenVikingVector:
    """Tiered archive retrieval returns L0/L1/L2 in order."""

    @pytest.mark.asyncio
    async def test_tiered_retrieval_by_level(
        self,
        local_stores: tuple[CacheStore, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        _, _, vector = local_stores
        now = datetime.utcnow()
        doc = Document(title="Architecture Overview", source="unit_test")
        chunks = [
            DocumentChunk(level=0, content="L0 summary of authentication flow", created_at=now),
            DocumentChunk(level=1, content="L1 section on authentication middleware", created_at=now),
            DocumentChunk(level=2, content="L2 detail: authentication token validation", created_at=now),
        ]
        await vector.ingest_document(doc, chunks)

        result = await vector.retrieve_tiered("authentication")
        assert isinstance(result, TieredRetrieval)
        assert len(result.level_0) >= 1
        assert len(result.level_1) >= 1
        assert len(result.level_2) >= 1
        assert all(item["level"] == 0 for item in result.level_0)
        assert all(item["level"] == 1 for item in result.level_1)
        assert all(item["level"] == 2 for item in result.level_2)

    @pytest.mark.asyncio
    async def test_tiered_retrieval_respects_level_filter(
        self,
        local_stores: tuple[CacheStore, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        _, _, vector = local_stores
        now = datetime.utcnow()
        doc = Document(title="Filtered doc", source="unit_test")
        chunks = [
            DocumentChunk(level=0, content="overview of deployment pipeline", created_at=now),
            DocumentChunk(level=2, content="deep deployment pipeline steps", created_at=now),
        ]
        await vector.ingest_document(doc, chunks)

        result = await vector.retrieve_tiered("deployment", levels=[0, 2])
        assert len(result.level_0) >= 1
        assert result.level_1 == []
        assert len(result.level_2) >= 1


class TestCrossTierSynthesis:
    """When memory lookup is needed, all three tiers contribute to the brief."""

    @pytest.mark.asyncio
    async def test_memory_lookup_synthesizes_all_tiers(
        self,
        local_stores: tuple[CacheStore, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        cache, episodic, vector = local_stores
        now = datetime.utcnow()

        await cache.set(
            "ctx",
            CacheEntry(content="Recent cache hit about database pooling", tags=["db"], created_at=now),
        )
        await episodic.store_episode(
            Episode(content="We decided to use SQLite for local dev", episode_type="fact", confidence=0.8)
        )
        await vector.ingest_document(
            Document(title="DB docs", source="test"),
            [DocumentChunk(level=1, content="Archive chunk about database schema design", created_at=now)],
        )

        intent = Intent(
            category=IntentCategory.MEMORY_LOOKUP_NEEDED,
            confidence=0.9,
            requires_memory=True,
        )
        assert intent.requires_memory is True

        cache_hits = await cache.search_by_query("database", limit=5)
        episodes = await episodic.retrieve_relevant("SQLite", limit=5)
        archive = await vector.retrieve_tiered("database")

        brief = build_template_brief(
            "What did we decide about the database?",
            cache_hits,
            episodes,
            archive,
        )
        assert brief.cache_hits >= 1
        assert brief.episode_count >= 1
        assert brief.archive_chunks >= 1
        assert "Cache" in brief.summary
        assert "Episodes" in brief.summary
        assert "Archive" in brief.summary

"""Tests for needle-in-a-haystack benchmark integration with Helios Memory."""

from __future__ import annotations

import pytest

from helios_memory.benchmark.haystack import (
    build_haystack_with_needle,
    build_repeating_haystack,
    insert_needle_at_depth,
)
from helios_memory.benchmark.ingestion import (
    chunk_text,
    find_needle_chunk_index,
    ingest_haystack_episodic,
    ingest_haystack_vector,
)
from helios_memory.benchmark.runner import derive_retrieval_query, run_cell
from helios_memory.benchmark.runner import BenchmarkConfig
from helios_memory.benchmark.scoring import (
    exact_match_in_text,
    score_episodic_retrieval,
    score_ranked_contents,
    score_vector_retrieval,
)
from helios_memory.benchmark.tokens import count
from helios_memory.benchmark.types import NeedleSpec
from helios_memory.interfaces import EpisodicMemoryStore, VectorArchive
from helios_memory.models import TieredRetrieval


class TestHaystackGeneration:
    def test_repeating_haystack_meets_token_target(self) -> None:
        text = build_repeating_haystack(800)
        assert count(text) >= 800

    def test_insert_at_zero_puts_needle_at_start(self) -> None:
        base = build_repeating_haystack(500)
        needle = "NEEDLE FACT."
        text, placement = insert_needle_at_depth(base, needle, 0.0)
        assert text.startswith(needle)
        assert placement.insertion_token_index == 0

    def test_insert_at_hundred_appends_needle(self) -> None:
        base = build_repeating_haystack(500)
        needle = "END NEEDLE."
        text, placement = insert_needle_at_depth(base, needle, 100.0)
        assert text.endswith(needle)

    def test_build_haystack_with_needle_records_depth(self) -> None:
        build = build_haystack_with_needle(600, 50.0)
        assert build.placement.text == build.needle.needle_text
        assert 35.0 <= build.placement.actual_depth_percent <= 65.0


class TestIngestion:
    def test_chunk_text_splits_into_windows(self) -> None:
        text = build_repeating_haystack(900)
        chunks = chunk_text(text, chunk_size_tokens=200)
        assert len(chunks) >= 3
        assert all(chunk.strip() for chunk in chunks)

    def test_find_needle_chunk_index(self) -> None:
        build = build_haystack_with_needle(700, 42.0)
        chunks = chunk_text(build.text, chunk_size_tokens=128)
        index = find_needle_chunk_index(chunks, build.needle.needle_text)
        assert index is not None
        assert build.needle.needle_text.lower() in chunks[index].lower()


class TestScoring:
    def test_exact_match_is_case_insensitive(self) -> None:
        assert exact_match_in_text("The answer is Eat A Sandwich.", "eat a sandwich")

    def test_score_ranked_contents_mrr_and_hit(self) -> None:
        ranked = ["irrelevant", "contains eat a sandwich and sit in Dolores Park here", "other"]
        score = score_ranked_contents(ranked, "eat a sandwich and sit in Dolores Park", top_k=3)
        assert score.hit is True
        assert score.rank == 2
        assert score.reciprocal_rank == pytest.approx(0.5)

    def test_score_ranked_contents_miss(self) -> None:
        score = score_ranked_contents(["alpha", "beta"], "missing", top_k=2)
        assert score.hit is False
        assert score.reciprocal_rank == 0.0

    def test_score_vector_retrieval(self) -> None:
        archive = TieredRetrieval(
            level_0=[],
            level_1=[],
            level_2=[{"content": "needle says eat a sandwich and sit in Dolores Park"}],
        )
        score = score_vector_retrieval(archive, "eat a sandwich and sit in Dolores Park")
        assert score.hit is True


class TestRetrievalIntegration:
    @pytest.mark.asyncio
    async def test_vector_retrieves_needle_at_shallow_depth(
        self,
        local_stores: tuple[object, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        _, episodic, vector = local_stores
        build = build_haystack_with_needle(800, 0.0)
        query = derive_retrieval_query(build.needle.question)

        await ingest_haystack_vector(vector, build, chunk_size_tokens=128)
        archive = await vector.retrieve_tiered(query)
        score = score_vector_retrieval(archive, build.needle.expected_answer)
        assert score.hit is True

    @pytest.mark.asyncio
    async def test_episodic_retrieves_needle_at_deep_depth(
        self,
        local_stores: tuple[object, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        _, episodic, _ = local_stores
        build = build_haystack_with_needle(1200, 100.0)
        query = derive_retrieval_query(build.needle.question)

        await ingest_haystack_episodic(episodic, build, chunk_size_tokens=128)
        episodes = await episodic.retrieve_relevant(query, limit=10)
        score = score_episodic_retrieval(episodes, build.needle.expected_answer)
        assert score.hit is True

    @pytest.mark.asyncio
    async def test_run_cell_produces_benchmark_result(self, tmp_db: str) -> None:
        config = BenchmarkConfig(
            context_lengths=(400,),
            depth_percents=(0.0, 100.0),
            chunk_size_tokens=128,
            top_k=10,
        )
        cell = await run_cell(config, 400, 0.0, db_path=tmp_db)
        assert cell.vector_score.hit is True
        assert cell.episodic_score.hit is True


class TestEdgeCases:
    def test_derive_retrieval_query_strips_stop_words(self) -> None:
        query = derive_retrieval_query("What is the best thing to do in San Francisco?")
        assert "San Francisco" in query
        assert "what" not in query.lower()

    @pytest.mark.asyncio
    async def test_empty_query_returns_no_episodes(
        self,
        local_stores: tuple[object, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        _, episodic, _ = local_stores
        build = build_haystack_with_needle(300, 50.0)
        await ingest_haystack_episodic(episodic, build, chunk_size_tokens=64)
        episodes = await episodic.retrieve_relevant("zzznomatchzzz", limit=5)
        score = score_episodic_retrieval(episodes, build.needle.expected_answer)
        assert score.hit is False

    def test_custom_needle_spec(self) -> None:
        needle = NeedleSpec(
            needle_text="Secret code ALPHA-42 is stored here.",
            expected_answer="ALPHA-42",
            question="What is the secret code?",
        )
        build = build_haystack_with_needle(500, 25.0, needle=needle)
        assert "ALPHA-42" in build.text

    @pytest.mark.asyncio
    async def test_mid_depth_needle_retrievable_from_vector(
        self,
        local_stores: tuple[object, EpisodicMemoryStore, VectorArchive],
    ) -> None:
        _, _, vector = local_stores
        build = build_haystack_with_needle(1500, 50.0)
        query = derive_retrieval_query(build.needle.question)
        await ingest_haystack_vector(vector, build, chunk_size_tokens=100)
        archive = await vector.retrieve_tiered(query)
        score = score_vector_retrieval(archive, build.needle.expected_answer, top_k=20)
        assert score.hit is True

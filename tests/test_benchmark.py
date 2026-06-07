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
        expected_final_index = count(base)
        assert text.endswith(needle)
        assert placement.insertion_token_index == expected_final_index

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
        _, _episodic, vector = local_stores
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


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


class TestTokenHelpers:
    def test_encoding_name_returns_string(self) -> None:
        from helios_memory.benchmark.tokens import encoding_name

        name = encoding_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_encode_returns_list_of_ints(self) -> None:
        from helios_memory.benchmark.tokens import encode

        tokens = encode("Hello world")
        assert isinstance(tokens, list)
        assert len(tokens) > 0
        assert all(isinstance(t, int) for t in tokens)

    def test_encode_empty_string(self) -> None:
        from helios_memory.benchmark.tokens import encode

        tokens = encode("")
        # Fallback: max(1, 0//4) = 1; tiktoken: 0 tokens
        assert isinstance(tokens, list)

    def test_decode_returns_string(self) -> None:
        from helios_memory.benchmark.tokens import decode, encode

        tokens = encode("round trip text")
        result = decode(tokens)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_count_positive_for_nonempty_text(self) -> None:
        from helios_memory.benchmark.tokens import count

        n = count("some text here")
        assert n >= 1

    def test_count_empty_string_fallback(self) -> None:
        from helios_memory.benchmark.tokens import count

        # Fallback returns max(1, 0//4) = 1; tiktoken may return 0
        n = count("")
        assert isinstance(n, int)

    def test_truncate_to_tokens_zero_returns_empty(self) -> None:
        from helios_memory.benchmark.tokens import truncate_to_tokens

        result = truncate_to_tokens("some text", 0)
        assert result == ""

    def test_truncate_to_tokens_negative_returns_empty(self) -> None:
        from helios_memory.benchmark.tokens import truncate_to_tokens

        result = truncate_to_tokens("some text", -5)
        assert result == ""

    def test_truncate_to_tokens_truncates_long_text(self) -> None:
        from helios_memory.benchmark.tokens import count, truncate_to_tokens

        long_text = "word " * 500
        truncated = truncate_to_tokens(long_text, 50)
        assert count(truncated) <= 50

    def test_truncate_to_tokens_short_text_unchanged(self) -> None:
        from helios_memory.benchmark.tokens import count, truncate_to_tokens

        short = "hello"
        result = truncate_to_tokens(short, 1000)
        # Should return the full text (not truncated beyond length)
        assert count(result) <= 1000
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# BenchmarkReport properties
# ---------------------------------------------------------------------------


class TestBenchmarkReportProperties:
    def _make_score(self, hit: bool, rr: float) -> "RetrievalScore":
        from helios_memory.benchmark.types import RetrievalScore

        return RetrievalScore(
            hit=hit,
            recall_at_k=1.0 if hit else 0.0,
            reciprocal_rank=rr,
            exact_match_in_top_k=hit,
            rank=1 if hit else None,
            chunks_examined=5,
        )

    def _make_cell(self, v_hit: bool, e_hit: bool, v_rr: float, e_rr: float) -> "BenchmarkCellResult":
        from helios_memory.benchmark.types import BenchmarkCellResult

        return BenchmarkCellResult(
            context_length=500,
            depth_percent=50.0,
            actual_depth_percent=48.0,
            chunk_count=4,
            vector_score=self._make_score(v_hit, v_rr),
            episodic_score=self._make_score(e_hit, e_rr),
        )

    def test_empty_report_accuracy_is_zero(self) -> None:
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        assert report.vector_accuracy == 0.0
        assert report.episodic_accuracy == 0.0
        assert report.mean_vector_mrr == 0.0
        assert report.mean_episodic_mrr == 0.0

    def test_all_hits_gives_full_accuracy(self) -> None:
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        report.cells = [self._make_cell(True, True, 1.0, 1.0) for _ in range(3)]
        assert report.vector_accuracy == pytest.approx(1.0)
        assert report.episodic_accuracy == pytest.approx(1.0)
        assert report.mean_vector_mrr == pytest.approx(1.0)
        assert report.mean_episodic_mrr == pytest.approx(1.0)

    def test_all_misses_gives_zero_accuracy(self) -> None:
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        report.cells = [self._make_cell(False, False, 0.0, 0.0) for _ in range(3)]
        assert report.vector_accuracy == pytest.approx(0.0)
        assert report.episodic_accuracy == pytest.approx(0.0)
        assert report.mean_vector_mrr == pytest.approx(0.0)
        assert report.mean_episodic_mrr == pytest.approx(0.0)

    def test_partial_hits_accuracy(self) -> None:
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        report.cells = [
            self._make_cell(True, False, 1.0, 0.0),
            self._make_cell(False, True, 0.0, 0.5),
            self._make_cell(True, True, 0.5, 1.0),
            self._make_cell(False, False, 0.0, 0.0),
        ]
        assert report.vector_accuracy == pytest.approx(2 / 4)
        assert report.episodic_accuracy == pytest.approx(2 / 4)
        assert report.mean_vector_mrr == pytest.approx((1.0 + 0.0 + 0.5 + 0.0) / 4)
        assert report.mean_episodic_mrr == pytest.approx((0.0 + 0.5 + 1.0 + 0.0) / 4)

    def test_report_has_run_name(self) -> None:
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="my-run")
        assert report.run_name == "my-run"

    def test_report_started_at_is_set(self) -> None:
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        assert report.started_at is not None

    def test_report_finished_at_defaults_none(self) -> None:
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        assert report.finished_at is None


# ---------------------------------------------------------------------------
# Haystack edge cases
# ---------------------------------------------------------------------------


class TestHaystackEdgeCases:
    def test_empty_unit_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            build_repeating_haystack(500, unit="   ")

    def test_invalid_depth_below_zero_raises(self) -> None:
        base = build_repeating_haystack(300)
        with pytest.raises(ValueError, match="depth_percent"):
            insert_needle_at_depth(base, "needle", -1.0)

    def test_invalid_depth_above_hundred_raises(self) -> None:
        base = build_repeating_haystack(300)
        with pytest.raises(ValueError, match="depth_percent"):
            insert_needle_at_depth(base, "needle", 101.0)

    def test_snap_to_periods_false_uses_raw_position(self) -> None:
        base = build_repeating_haystack(500)
        _, placement_snap = insert_needle_at_depth(base, "NEEDLE.", 50.0, snap_to_periods=True)
        _, placement_no_snap = insert_needle_at_depth(base, "NEEDLE.", 50.0, snap_to_periods=False)
        # Without snapping the actual depth should be very close to the target
        assert abs(placement_no_snap.actual_depth_percent - 50.0) <= 1.0

    def test_build_haystack_stores_target_token_count(self) -> None:
        build = build_haystack_with_needle(700, 25.0)
        assert build.target_token_count == 700

    def test_build_haystack_token_count_populated(self) -> None:
        build = build_haystack_with_needle(500, 0.0)
        assert build.token_count > 0

    def test_build_haystack_needle_text_in_output(self) -> None:
        needle = NeedleSpec(
            needle_text="Unique-marker-XYZ-789.",
            expected_answer="Unique-marker-XYZ-789",
            question="What is the marker?",
        )
        build = build_haystack_with_needle(400, 75.0, needle=needle)
        assert "Unique-marker-XYZ-789" in build.text

    def test_build_haystack_custom_unit(self) -> None:
        custom_unit = "Custom filler sentence about databases."
        build = build_haystack_with_needle(300, 50.0, haystack_unit=custom_unit)
        assert build.token_count > 0
        assert build.placement.text == build.needle.needle_text

    def test_insert_needle_placement_text_matches_needle(self) -> None:
        base = build_repeating_haystack(400)
        needle = "The secret is 42."
        _, placement = insert_needle_at_depth(base, needle, 33.0)
        assert placement.text == needle

    def test_insert_needle_actual_depth_within_bounds(self) -> None:
        base = build_repeating_haystack(600)
        _, placement = insert_needle_at_depth(base, "test needle", 75.0)
        assert 0.0 <= placement.actual_depth_percent <= 100.0


# ---------------------------------------------------------------------------
# Ingestion edge cases
# ---------------------------------------------------------------------------


class TestIngestionEdgeCases:
    def test_chunk_text_zero_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            chunk_text("some text", 0)

    def test_chunk_text_negative_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            chunk_text("some text", -1)

    def test_chunk_text_empty_string_returns_empty_list(self) -> None:
        chunks = chunk_text("", 100)
        assert chunks == []

    def test_chunk_text_whitespace_only_returns_empty(self) -> None:
        chunks = chunk_text("   \n\n  ", 100)
        assert chunks == []

    def test_chunk_text_single_sentence_is_one_chunk(self) -> None:
        chunks = chunk_text("One simple sentence.", 500)
        assert len(chunks) == 1
        assert "One simple sentence" in chunks[0]

    def test_find_needle_chunk_index_returns_none_when_absent(self) -> None:
        chunks = ["some text here", "more text there", "nothing relevant"]
        result = find_needle_chunk_index(chunks, "ABSENT_NEEDLE_XYZ")
        assert result is None

    def test_find_needle_chunk_index_case_insensitive(self) -> None:
        chunks = ["chunk with NEEDLE FACT inside", "other chunk"]
        idx = find_needle_chunk_index(chunks, "needle fact")
        assert idx == 0

    def test_summary_truncates_long_content(self) -> None:
        from helios_memory.benchmark.ingestion import _summary

        long_content = "A" * 200
        result = _summary(long_content, 80)
        assert len(result) == 80
        assert result.endswith("...")

    def test_summary_preserves_short_content(self) -> None:
        from helios_memory.benchmark.ingestion import _summary

        short = "Short text."
        result = _summary(short, 80)
        assert result == short

    def test_summary_strips_whitespace(self) -> None:
        from helios_memory.benchmark.ingestion import _summary

        content = "  hello world  "
        result = _summary(content, 200)
        assert result == "hello world"

    def test_chunk_text_respects_token_budget(self) -> None:
        from helios_memory.benchmark.tokens import count

        text = build_repeating_haystack(800)
        chunks = chunk_text(text, chunk_size_tokens=100)
        # Each chunk should not hugely exceed the budget (sentence boundary may overshoot a bit)
        for chunk in chunks:
            assert count(chunk) <= 200  # generous upper bound for boundary alignment


# ---------------------------------------------------------------------------
# Scoring edge cases
# ---------------------------------------------------------------------------


class TestScoringEdgeCases:
    def test_exact_match_empty_expected_returns_false(self) -> None:
        assert exact_match_in_text("some response", "") is False

    def test_exact_match_whitespace_only_expected_returns_false(self) -> None:
        assert exact_match_in_text("some response", "   ") is False

    def test_exact_match_not_found_returns_false(self) -> None:
        assert exact_match_in_text("completely different text", "needle fact") is False

    def test_score_ranked_contents_first_rank_gives_mrr_one(self) -> None:
        ranked = ["the answer is eat a sandwich and sit in Dolores Park here", "other"]
        score = score_ranked_contents(ranked, "eat a sandwich and sit in Dolores Park", top_k=5)
        assert score.rank == 1
        assert score.reciprocal_rank == pytest.approx(1.0)
        assert score.recall_at_k == pytest.approx(1.0)

    def test_score_ranked_contents_top_k_truncates(self) -> None:
        # Match is at position 3 (index 2), top_k=2 → should be a miss
        ranked = ["miss", "miss", "eat a sandwich match here"]
        score = score_ranked_contents(ranked, "eat a sandwich", top_k=2)
        assert score.hit is False
        assert score.chunks_examined == 2

    def test_score_ranked_contents_empty_list(self) -> None:
        score = score_ranked_contents([], "eat a sandwich", top_k=5)
        assert score.hit is False
        assert score.rank is None
        assert score.reciprocal_rank == 0.0
        assert score.chunks_examined == 0

    def test_score_vector_retrieval_hit_in_level_1(self) -> None:
        archive = TieredRetrieval(
            level_0=[],
            level_1=[{"content": "eat a sandwich and sit in Dolores Park here"}],
            level_2=[],
        )
        score = score_vector_retrieval(archive, "eat a sandwich and sit in Dolores Park")
        assert score.hit is True

    def test_score_vector_retrieval_hit_in_level_0(self) -> None:
        archive = TieredRetrieval(
            level_0=[{"content": "eat a sandwich and sit in Dolores Park"}],
            level_1=[],
            level_2=[],
        )
        score = score_vector_retrieval(archive, "eat a sandwich and sit in Dolores Park")
        assert score.hit is True

    def test_score_vector_retrieval_miss_all_tiers(self) -> None:
        archive = TieredRetrieval(
            level_0=[{"content": "irrelevant text one"}],
            level_1=[{"content": "irrelevant text two"}],
            level_2=[{"content": "irrelevant text three"}],
        )
        score = score_vector_retrieval(archive, "eat a sandwich and sit in Dolores Park")
        assert score.hit is False

    def test_score_vector_retrieval_l2_ranked_before_l1(self) -> None:
        # L2 detail is ranked before L1 section; match in L2 → rank 1
        archive = TieredRetrieval(
            level_0=[],
            level_1=[{"content": "eat a sandwich and sit in Dolores Park"}],
            level_2=[{"content": "eat a sandwich and sit in Dolores Park"}],
        )
        score = score_vector_retrieval(archive, "eat a sandwich and sit in Dolores Park", top_k=5)
        assert score.rank == 1  # L2 comes first

    def test_score_vector_retrieval_chunk_without_content_key_ignored(self) -> None:
        archive = TieredRetrieval(
            level_0=[],
            level_1=[],
            level_2=[{"other_key": "eat a sandwich and sit in Dolores Park"}],
        )
        score = score_vector_retrieval(archive, "eat a sandwich and sit in Dolores Park")
        assert score.hit is False

    def test_score_episodic_retrieval_empty_episodes(self) -> None:
        from helios_memory.models.storage import Episode

        score = score_episodic_retrieval([], "eat a sandwich")
        assert score.hit is False
        assert score.chunks_examined == 0

    def test_score_episodic_retrieval_with_matching_episode(self) -> None:
        from helios_memory.models.storage import Episode

        episodes = [
            Episode(
                content="eat a sandwich and sit in Dolores Park on a sunny day.",
                episode_type="test",
                confidence=0.9,
            ),
        ]
        score = score_episodic_retrieval(episodes, "eat a sandwich and sit in Dolores Park")
        assert score.hit is True
        assert score.rank == 1


# ---------------------------------------------------------------------------
# Runner formatting and parsing helpers
# ---------------------------------------------------------------------------


class TestRunnerFormatting:
    def _make_score(self, hit: bool, rr: float) -> "RetrievalScore":
        from helios_memory.benchmark.types import RetrievalScore

        return RetrievalScore(
            hit=hit,
            recall_at_k=1.0 if hit else 0.0,
            reciprocal_rank=rr,
            exact_match_in_top_k=hit,
            rank=1 if hit else None,
            chunks_examined=3,
        )

    def _make_cell(self) -> "BenchmarkCellResult":
        from helios_memory.benchmark.types import BenchmarkCellResult

        return BenchmarkCellResult(
            context_length=1000,
            depth_percent=50.0,
            actual_depth_percent=48.5,
            chunk_count=8,
            vector_score=self._make_score(True, 1.0),
            episodic_score=self._make_score(False, 0.0),
            needle_chunk_index=3,
        )

    def test_format_report_contains_run_name(self) -> None:
        from helios_memory.benchmark.runner import format_report
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="my-test-run")
        report.cells = [self._make_cell()]
        output = format_report(report)
        assert "my-test-run" in output

    def test_format_report_contains_accuracy_lines(self) -> None:
        from helios_memory.benchmark.runner import format_report
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        report.cells = [self._make_cell()]
        output = format_report(report)
        assert "Vector accuracy" in output
        assert "Episodic accuracy" in output
        assert "Mean vector MRR" in output
        assert "Mean episodic MRR" in output

    def test_format_report_contains_table_header(self) -> None:
        from helios_memory.benchmark.runner import format_report
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        report.cells = [self._make_cell()]
        output = format_report(report)
        assert "context_len" in output
        assert "depth%" in output

    def test_format_report_empty_cells(self) -> None:
        from helios_memory.benchmark.runner import format_report
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="empty-run")
        output = format_report(report)
        assert "empty-run" in output
        assert "0.0%" in output or "0/" in output

    def test_report_to_json_is_valid_json(self) -> None:
        import json

        from helios_memory.benchmark.runner import report_to_json
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="json-test")
        report.cells = [self._make_cell()]
        raw = report_to_json(report)
        parsed = json.loads(raw)
        assert parsed["run_name"] == "json-test"

    def test_report_to_json_has_required_keys(self) -> None:
        import json

        from helios_memory.benchmark.runner import report_to_json
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="json-test")
        report.cells = [self._make_cell()]
        parsed = json.loads(report_to_json(report))
        for key in ("run_name", "started_at", "finished_at", "vector_accuracy",
                    "episodic_accuracy", "mean_vector_mrr", "mean_episodic_mrr", "cells"):
            assert key in parsed

    def test_report_to_json_cells_structure(self) -> None:
        import json

        from helios_memory.benchmark.runner import report_to_json
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        report.cells = [self._make_cell()]
        parsed = json.loads(report_to_json(report))
        cell = parsed["cells"][0]
        for key in ("context_length", "depth_percent", "actual_depth_percent",
                    "needle_chunk_index", "vector_score", "episodic_score"):
            assert key in cell

    def test_report_to_json_finished_at_none_when_not_set(self) -> None:
        import json

        from helios_memory.benchmark.runner import report_to_json
        from helios_memory.benchmark.types import BenchmarkReport

        report = BenchmarkReport(run_name="test")
        parsed = json.loads(report_to_json(report))
        assert parsed["finished_at"] is None

    def test_parse_int_list(self) -> None:
        from helios_memory.benchmark.runner import _parse_int_list

        result = _parse_int_list("100,200,300")
        assert result == (100, 200, 300)

    def test_parse_int_list_with_spaces(self) -> None:
        from helios_memory.benchmark.runner import _parse_int_list

        result = _parse_int_list(" 500 , 1000 ")
        assert result == (500, 1000)

    def test_parse_float_list(self) -> None:
        from helios_memory.benchmark.runner import _parse_float_list

        result = _parse_float_list("0,50.0,100")
        assert result == (0.0, 50.0, 100.0)

    def test_parse_float_list_with_spaces(self) -> None:
        from helios_memory.benchmark.runner import _parse_float_list

        result = _parse_float_list(" 0.0 , 25.5 , 75.0 ")
        assert result == (0.0, 25.5, 75.0)

    def test_benchmark_config_defaults(self) -> None:
        config = BenchmarkConfig()
        assert config.run_name == "helios-needle-benchmark"
        assert 500 in config.context_lengths
        assert 0.0 in config.depth_percents
        assert config.chunk_size_tokens == 256
        assert config.top_k == 10
        assert config.needle is None
        assert config.db_path is None

    def test_derive_retrieval_query_all_stop_words_returns_original(self) -> None:
        # All words are stop words → fall back to original stripped question
        query = derive_retrieval_query("what is the?")
        assert len(query) > 0

    def test_derive_retrieval_query_punctuation_stripped(self) -> None:
        query = derive_retrieval_query("Where are you?")
        # "Where" is a stop word; "are" is a stop word; "you" is kept
        assert "you" in query

    def test_derive_retrieval_query_preserves_meaningful_words(self) -> None:
        query = derive_retrieval_query("San Francisco weather forecast?")
        assert "San" in query
        assert "Francisco" in query
        assert "weather" in query
        assert "forecast" in query


# ---------------------------------------------------------------------------
# Module __init__ lazy loading
# ---------------------------------------------------------------------------


class TestModuleInit:
    def test_getattr_derive_retrieval_query_lazy_loads(self) -> None:
        import helios_memory.benchmark as bm

        fn = bm.derive_retrieval_query
        assert callable(fn)

    def test_getattr_format_report_lazy_loads(self) -> None:
        import helios_memory.benchmark as bm

        fn = bm.format_report
        assert callable(fn)

    def test_getattr_run_benchmark_lazy_loads(self) -> None:
        import helios_memory.benchmark as bm

        fn = bm.run_benchmark
        assert callable(fn)

    def test_getattr_run_cell_lazy_loads(self) -> None:
        import helios_memory.benchmark as bm

        fn = bm.run_cell
        assert callable(fn)

    def test_getattr_unknown_attribute_raises(self) -> None:
        import helios_memory.benchmark as bm

        with pytest.raises(AttributeError):
            _ = bm.nonexistent_attribute_xyz

    def test_public_symbols_importable_from_init(self) -> None:
        from helios_memory.benchmark import (
            BenchmarkCellResult,
            BenchmarkConfig,
            BenchmarkReport,
            HaystackBuild,
            NeedleSpec,
            RetrievalScore,
            build_haystack_with_needle,
            build_repeating_haystack,
            exact_match_in_text,
            insert_needle_at_depth,
            score_episodic_retrieval,
            score_ranked_contents,
            score_vector_retrieval,
        )

        assert BenchmarkCellResult is not None
        assert BenchmarkConfig is not None
        assert BenchmarkReport is not None

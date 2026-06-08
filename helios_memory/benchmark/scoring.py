"""Retrieval scoring for needle benchmarks (NIAH exact match + EncouRAGe IR metrics)."""

from __future__ import annotations

from typing import Any

from helios_memory.benchmark.types import RetrievalScore
from helios_memory.models import TieredRetrieval
from helios_memory.models.storage import Episode


def _normalize(text: str) -> str:
    return text.strip().lower()


def exact_match_in_text(response: str, expected_answer: str) -> bool:
    """Case-insensitive substring match (NIAH ExactMatchScorer semantics)."""
    if not expected_answer.strip():
        return False
    return _normalize(expected_answer) in _normalize(response)


def _chunk_contents(chunks: list[dict[str, Any]]) -> list[str]:
    contents: list[str] = []
    for chunk in chunks:
        value = chunk.get("content")
        if isinstance(value, str):
            contents.append(value)
    return contents


def score_ranked_contents(
    ranked_contents: list[str],
    expected_answer: str,
    *,
    top_k: int = 10,
) -> RetrievalScore:
    """Compute HitRate@k, Recall@k, and MRR for ranked retrieval results."""
    examined = ranked_contents[:top_k]
    normalized_expected = _normalize(expected_answer)
    if not normalized_expected:
        return RetrievalScore(
            hit=False,
            recall_at_k=0.0,
            reciprocal_rank=0.0,
            exact_match_in_top_k=False,
            rank=None,
            chunks_examined=len(examined),
        )
    rank: int | None = None
    for i, content in enumerate(examined, start=1):
        if normalized_expected in _normalize(content):
            rank = i
            break

    hit = rank is not None
    recall_at_k = 1.0 if hit else 0.0
    reciprocal_rank = (1.0 / rank) if rank else 0.0
    return RetrievalScore(
        hit=hit,
        recall_at_k=recall_at_k,
        reciprocal_rank=reciprocal_rank,
        exact_match_in_top_k=hit,
        rank=rank,
        chunks_examined=len(examined),
    )


def score_vector_retrieval(
    archive: TieredRetrieval,
    expected_answer: str,
    *,
    top_k: int = 10,
) -> RetrievalScore:
    """Score tiered archive retrieval — L2 first (detail), then L1, L0."""
    ranked = (
        _chunk_contents(archive.level_2)
        + _chunk_contents(archive.level_1)
        + _chunk_contents(archive.level_0)
    )
    return score_ranked_contents(ranked, expected_answer, top_k=top_k)


def score_episodic_retrieval(
    episodes: list[Episode],
    expected_answer: str,
    *,
    top_k: int = 10,
) -> RetrievalScore:
    """Score episodic retrieval results."""
    ranked = [episode.content for episode in episodes]
    return score_ranked_contents(ranked, expected_answer, top_k=top_k)

"""Benchmark result types for needle-in-haystack evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class NeedleSpec:
    """Single-fact needle configuration (NIAH single-needle task)."""

    needle_text: str = (
        "The best thing to do in San Francisco is eat a sandwich "
        "and sit in Dolores Park on a sunny day."
    )
    expected_answer: str = "eat a sandwich and sit in Dolores Park"
    question: str = "What is the best thing to do in San Francisco?"


@dataclass(slots=True)
class NeedlePlacement:
    """Where the needle landed in the haystack token stream."""

    text: str
    insertion_token_index: int
    actual_depth_percent: float


@dataclass(slots=True)
class HaystackBuild:
    """Haystack text with an embedded needle."""

    text: str
    token_count: int
    target_token_count: int
    depth_percent: float
    placement: NeedlePlacement
    needle: NeedleSpec


@dataclass(slots=True)
class RetrievalScore:
    """Retrieval metrics aligned with EncouRAGe IR metrics and NIAH exact match."""

    hit: bool
    recall_at_k: float
    reciprocal_rank: float
    exact_match_in_top_k: bool
    rank: int | None = None
    chunks_examined: int = 0


@dataclass(slots=True)
class BenchmarkCellResult:
    """One (context_length × depth) benchmark cell."""

    context_length: int
    depth_percent: float
    actual_depth_percent: float
    chunk_count: int
    vector_score: RetrievalScore
    episodic_score: RetrievalScore
    needle_chunk_index: int | None = None


@dataclass(slots=True)
class BenchmarkReport:
    """Aggregate benchmark output."""

    run_name: str
    cells: list[BenchmarkCellResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None

    @property
    def vector_accuracy(self) -> float:
        if not self.cells:
            return 0.0
        return sum(1 for cell in self.cells if cell.vector_score.hit) / len(self.cells)

    @property
    def episodic_accuracy(self) -> float:
        if not self.cells:
            return 0.0
        return sum(1 for cell in self.cells if cell.episodic_score.hit) / len(self.cells)

    @property
    def mean_vector_mrr(self) -> float:
        if not self.cells:
            return 0.0
        return sum(cell.vector_score.reciprocal_rank for cell in self.cells) / len(self.cells)

    @property
    def mean_episodic_mrr(self) -> float:
        if not self.cells:
            return 0.0
        return sum(cell.episodic_score.reciprocal_rank for cell in self.cells) / len(self.cells)

"""Needle-in-a-haystack benchmarking for Helios Memory retrieval tiers."""

from helios_memory.benchmark.haystack import (
    build_haystack_with_needle,
    build_repeating_haystack,
    insert_needle_at_depth,
)
from helios_memory.benchmark.runner import BenchmarkConfig
from helios_memory.benchmark.scoring import (
    exact_match_in_text,
    score_episodic_retrieval,
    score_ranked_contents,
    score_vector_retrieval,
)
from helios_memory.benchmark.types import (
    BenchmarkCellResult,
    BenchmarkReport,
    HaystackBuild,
    NeedleSpec,
    RetrievalScore,
)

__all__ = [
    "BenchmarkCellResult",
    "BenchmarkConfig",
    "BenchmarkReport",
    "HaystackBuild",
    "NeedleSpec",
    "RetrievalScore",
    "build_haystack_with_needle",
    "build_repeating_haystack",
    "exact_match_in_text",
    "insert_needle_at_depth",
    "score_episodic_retrieval",
    "score_ranked_contents",
    "score_vector_retrieval",
]


def __getattr__(name: str):
    if name in {
        "derive_retrieval_query",
        "format_report",
        "run_benchmark",
        "run_cell",
    }:
        from helios_memory.benchmark import runner as _runner

        return getattr(_runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

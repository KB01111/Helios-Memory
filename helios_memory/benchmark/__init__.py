"""Needle-in-a-haystack benchmarking for Helios Memory retrieval tiers."""

from typing import Any

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
    "derive_retrieval_query",
    "exact_match_in_text",
    "format_report",
    "insert_needle_at_depth",
    "run_benchmark",
    "run_cell",
    "score_episodic_retrieval",
    "score_ranked_contents",
    "score_vector_retrieval",
]

def __getattr__(name: str) -> Any:
    if name in {
        "derive_retrieval_query",
        "format_report",
        "run_benchmark",
        "run_cell",
    }:
        from helios_memory.benchmark import runner as _runner

        return getattr(_runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

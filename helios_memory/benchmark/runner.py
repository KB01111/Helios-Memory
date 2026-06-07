"""Needle-in-a-haystack benchmark runner for Helios Memory."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from helios_memory.benchmark.haystack import build_haystack_with_needle
from helios_memory.benchmark.ingestion import (
    chunk_text,
    ingest_haystack_episodic,
    ingest_haystack_vector,
)
from helios_memory.benchmark.scoring import score_episodic_retrieval, score_vector_retrieval
from helios_memory.benchmark.types import (
    BenchmarkCellResult,
    BenchmarkReport,
    NeedleSpec,
)
from helios_memory.providers.sqlite import SQLiteEpisodicStore, SQLiteVectorArchive

_QUERY_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "best",
        "do",
        "how",
        "in",
        "is",
        "of",
        "the",
        "thing",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
    }
)


@dataclass(slots=True)
class BenchmarkConfig:
    """Sweep configuration (NIAH-style context length × depth grid)."""

    run_name: str = "helios-needle-benchmark"
    context_lengths: tuple[int, ...] = (500, 1000, 2000)
    depth_percents: tuple[float, ...] = (0.0, 50.0, 100.0)
    chunk_size_tokens: int = 256
    top_k: int = 10
    needle: NeedleSpec | None = None
    db_path: str | None = None


def derive_retrieval_query(question: str) -> str:
    """Extract a keyword query suitable for Helios LIKE-based retrieval."""
    cleaned = question.replace("?", " ").replace("!", " ").replace(".", " ")
    words = [word.strip(".,!?\"'") for word in cleaned.split()]
    keywords = [word for word in words if word.lower() not in _QUERY_STOP_WORDS]
    if keywords:
        return " ".join(keywords)
    return question.strip()


async def run_cell(
    config: BenchmarkConfig,
    context_length: int,
    depth_percent: float,
    *,
    db_path: str,
) -> BenchmarkCellResult:
    """Execute one benchmark cell against fresh vector and episodic stores."""
    needle = config.needle or NeedleSpec()
    build = build_haystack_with_needle(context_length, depth_percent, needle=needle)
    query = derive_retrieval_query(needle.question)

    vector = SQLiteVectorArchive(db_path)
    episodic = SQLiteEpisodicStore(db_path)
    await vector.connect()
    await episodic.connect()
    try:
        _, _, needle_index = await ingest_haystack_vector(
            vector,
            build,
            chunk_size_tokens=config.chunk_size_tokens,
        )
        await ingest_haystack_episodic(
            episodic,
            build,
            chunk_size_tokens=config.chunk_size_tokens,
        )

        archive = await vector.retrieve_tiered(query)
        vector_score = score_vector_retrieval(
            archive,
            needle.expected_answer,
            top_k=config.top_k,
        )

        episodes = await episodic.retrieve_relevant(query, limit=config.top_k)
        episodic_score = score_episodic_retrieval(
            episodes,
            needle.expected_answer,
            top_k=config.top_k,
        )
    finally:
        await vector.close()
        await episodic.close()

    return BenchmarkCellResult(
        context_length=context_length,
        depth_percent=depth_percent,
        actual_depth_percent=build.placement.actual_depth_percent,
        chunk_count=len(chunk_text(build.text, config.chunk_size_tokens)),
        vector_score=vector_score,
        episodic_score=episodic_score,
        needle_chunk_index=needle_index,
    )


async def run_benchmark(config: BenchmarkConfig) -> BenchmarkReport:
    """Run the full context_length × depth_percent sweep."""
    report = BenchmarkReport(run_name=config.run_name)
    for context_length in config.context_lengths:
        for depth_percent in config.depth_percents:
            if config.db_path is None:
                # Separate in-memory DB per cell for isolation.
                cell_db = f"file:bench_{context_length}_{int(depth_percent)}?mode=memory&cache=shared"
            else:
                cell_db = config.db_path

            cell = await run_cell(
                config,
                context_length,
                depth_percent,
                db_path=cell_db,
            )
            report.cells.append(cell)
    report.finished_at = datetime.utcnow()
    return report


def format_report(report: BenchmarkReport) -> str:
    """Human-readable summary table."""
    lines = [
        f"Run: {report.run_name}",
        f"Vector accuracy: {report.vector_accuracy:.1%} ({sum(c.vector_score.hit for c in report.cells)}/{len(report.cells)})",
        f"Episodic accuracy: {report.episodic_accuracy:.1%} ({sum(c.episodic_score.hit for c in report.cells)}/{len(report.cells)})",
        f"Mean vector MRR: {report.mean_vector_mrr:.3f}",
        f"Mean episodic MRR: {report.mean_episodic_mrr:.3f}",
        "",
        "context_len | depth% | actual% | vector_hit | episodic_hit | v_mrr | e_mrr",
        "------------|--------|---------|------------|--------------|-------|------",
    ]
    for cell in report.cells:
        lines.append(
            f"{cell.context_length:11d} | {cell.depth_percent:6.0f} | "
            f"{cell.actual_depth_percent:7.1f} | "
            f"{'yes' if cell.vector_score.hit else 'no ':>10} | "
            f"{'yes' if cell.episodic_score.hit else 'no ':>12} | "
            f"{cell.vector_score.reciprocal_rank:5.2f} | {cell.episodic_score.reciprocal_rank:5.2f}"
        )
    return "\n".join(lines)


def report_to_json(report: BenchmarkReport) -> str:
    payload = {
        "run_name": report.run_name,
        "started_at": report.started_at.isoformat(),
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        "vector_accuracy": report.vector_accuracy,
        "episodic_accuracy": report.episodic_accuracy,
        "mean_vector_mrr": report.mean_vector_mrr,
        "mean_episodic_mrr": report.mean_episodic_mrr,
        "cells": [
            {
                "context_length": cell.context_length,
                "depth_percent": cell.depth_percent,
                "actual_depth_percent": cell.actual_depth_percent,
                "needle_chunk_index": cell.needle_chunk_index,
                "vector_score": asdict(cell.vector_score),
                "episodic_score": asdict(cell.episodic_score),
            }
            for cell in report.cells
        ],
    }
    return json.dumps(payload, indent=2)


def _parse_int_list(value: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def _parse_float_list(value: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in value.split(",") if part.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Helios Memory needle-in-a-haystack retrieval benchmark.",
    )
    parser.add_argument(
        "--context-lengths",
        default="500,1000",
        help="Comma-separated target context token lengths (default: 500,1000)",
    )
    parser.add_argument(
        "--depth-percents",
        default="0,50,100",
        help="Comma-separated needle depth percentages (default: 0,50,100)",
    )
    parser.add_argument("--chunk-size", type=int, default=256, help="Chunk size in tokens")
    parser.add_argument("--top-k", type=int, default=10, help="Top-k for retrieval metrics")
    parser.add_argument("--run-name", default="helios-needle-benchmark")
    parser.add_argument("--json-out", type=Path, help="Optional path to write JSON results")
    args = parser.parse_args(argv)

    config = BenchmarkConfig(
        run_name=args.run_name,
        context_lengths=_parse_int_list(args.context_lengths),
        depth_percents=_parse_float_list(args.depth_percents),
        chunk_size_tokens=args.chunk_size,
        top_k=args.top_k,
    )
    report = asyncio.run(run_benchmark(config))
    print(format_report(report))
    if args.json_out:
        args.json_out.write_text(report_to_json(report), encoding="utf-8")
        print(f"\nWrote JSON results to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

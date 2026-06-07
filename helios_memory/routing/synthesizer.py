"""Template-based memory brief synthesis with optional LLM summarization."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from helios_memory.models import MemoryBrief, TieredRetrieval
from helios_memory.models.storage import CacheEntry, Episode

logger = logging.getLogger(__name__)

LLMSummarizeFn = Callable[[str, str], Awaitable[str | None]]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return max(1, len(text) // 4)


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        key = _normalize_text(line)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def _sort_cache_entries(entries: list[CacheEntry]) -> list[CacheEntry]:
    return sorted(
        entries,
        key=lambda entry: (entry.recency, entry.confidence, entry.created_at),
        reverse=True,
    )


def _sort_episodes(episodes: list[Episode]) -> list[Episode]:
    return sorted(
        episodes,
        key=lambda ep: (ep.confidence, ep.created_at),
        reverse=True,
    )


def _chunk_content(chunk: dict[str, Any]) -> str:
    for key in ("content", "text", "summary", "body"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _collect_archive_lines(archive: TieredRetrieval) -> list[str]:
    lines: list[str] = []
    for level, label in (
        (archive.level_0, "L0"),
        (archive.level_1, "L1"),
        (archive.level_2, "L2"),
    ):
        for chunk in level:
            content = _chunk_content(chunk)
            if content:
                lines.append(f"[{label}] {content}")
    return lines


def build_template_brief(
    prompt: str,
    cache: list[CacheEntry],
    episodes: list[Episode],
    archive: TieredRetrieval,
    max_tokens: int = 2000,
) -> MemoryBrief:
    """Pure template synthesis with dedup and recency weighting."""
    sections: list[str] = []
    sources: list[str] = []

    if cache:
        sections.append("## Cache")
        for entry in _sort_cache_entries(cache):
            sections.append(f"- {entry.content}")
            sources.append(f"cache:{entry.key or entry.source}")

    if episodes:
        sections.append("## Episodes")
        for episode in _sort_episodes(episodes):
            sections.append(f"- [{episode.episode_type}] {episode.content}")
            sources.append(f"episode:{episode.id or episode.episode_type}")

    archive_lines = _collect_archive_lines(archive)
    if archive_lines:
        sections.append("## Archive")
        sections.extend(f"- {line}" for line in archive_lines)
        sources.append("archive:tiered")

    if not sections:
        return MemoryBrief(summary="")

    deduped = _dedupe_lines(sections)
    summary_parts: list[str] = [f"Context for: {prompt.strip()[:200]}"]
    token_budget = max_tokens

    for line in deduped:
        line_tokens = _estimate_tokens(line)
        if _estimate_tokens("\n".join(summary_parts)) + line_tokens > token_budget:
            break
        summary_parts.append(line)

    summary = "\n".join(summary_parts)
    return MemoryBrief(
        summary=summary,
        cache_hits=len(cache),
        episode_count=len(episodes),
        archive_chunks=archive.total_chunks,
        token_estimate=_estimate_tokens(summary),
        sources=_dedupe_lines(sources),
        metadata={"synthesis": "template"},
    )


class MemorySynthesizer:
    """Combines retrieved context into a compact memory brief."""

    def __init__(
        self,
        max_tokens: int = 2000,
        llm: Any = None,
        llm_summarize: LLMSummarizeFn | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self._llm = llm
        self._llm_summarize = llm_summarize

    async def synthesize(
        self,
        prompt: str,
        cache: list[CacheEntry],
        episodes: list[Episode],
        archive: TieredRetrieval,
    ) -> MemoryBrief:
        """Synthesize brief via template; optionally compress with LLM."""
        brief = build_template_brief(
            prompt,
            cache,
            episodes,
            archive,
            max_tokens=self.max_tokens,
        )

        if brief.token_estimate > self.max_tokens:
            llm_summary = await self._try_llm_summarize(prompt, brief.summary)
            if llm_summary:
                return MemoryBrief(
                    summary=llm_summary,
                    cache_hits=brief.cache_hits,
                    episode_count=brief.episode_count,
                    archive_chunks=brief.archive_chunks,
                    token_estimate=_estimate_tokens(llm_summary),
                    sources=brief.sources,
                    metadata={**brief.metadata, "synthesis": "llm"},
                )

        return brief

    async def _try_llm_summarize(self, prompt: str, raw_summary: str) -> str | None:
        if not raw_summary.strip():
            return None

        if self._llm_summarize is not None:
            try:
                return await self._llm_summarize(prompt, raw_summary)
            except Exception:
                logger.exception("LLM summarize callback failed")
                return None

        if self._llm is None:
            return None

        summarize_fn = getattr(self._llm, "summarize", None)
        if callable(summarize_fn):
            try:
                result = summarize_fn(prompt, raw_summary)
                if hasattr(result, "__await__"):
                    return await result
                return str(result) if result is not None else None
            except Exception:
                logger.exception("LLM summarize failed")
                return None

        return None

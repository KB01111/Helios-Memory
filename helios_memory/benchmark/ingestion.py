"""Ingest haystack text into Helios memory tiers for retrieval evaluation."""

from __future__ import annotations

from datetime import datetime

from helios_memory.benchmark.tokens import count, decode, encode
from helios_memory.benchmark.types import HaystackBuild
from helios_memory.interfaces import EpisodicMemoryStore, VectorArchive
from helios_memory.models.storage import Document, DocumentChunk, Episode


def chunk_text(text: str, chunk_size_tokens: int) -> list[str]:
    """Split text into fixed-size token windows, preferring sentence boundaries."""
    if chunk_size_tokens <= 0:
        raise ValueError("chunk_size_tokens must be positive")

    sentences = [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]
    if not sentences:
        return [text] if text.strip() else []

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current}. {sentence}." if current else f"{sentence}."
        if count(candidate) <= chunk_size_tokens:
            current = candidate
        else:
            if current:
                chunks.append(current)
            single_candidate = f"{sentence}."
            if count(single_candidate) <= chunk_size_tokens:
                current = single_candidate
            else:
                # Fallback for an oversized sentence: hard token split.
                tokens = encode(single_candidate)
                for start in range(0, len(tokens), chunk_size_tokens):
                    window = tokens[start : start + chunk_size_tokens]
                    if window:
                        chunks.append(decode(window))
                current = ""

    if current:
        chunks.append(current)
    return chunks


def find_needle_chunk_index(chunks: list[str], needle_text: str) -> int | None:
    normalized = needle_text.strip().lower()
    for index, chunk in enumerate(chunks):
        if normalized in chunk.lower():
            return index
    return None


def _summary(content: str, max_chars: int) -> str:
    trimmed = content.strip()
    if len(trimmed) <= max_chars:
        return trimmed
    return trimmed[: max_chars - 3].rstrip() + "..."


async def ingest_haystack_vector(
    vector: VectorArchive,
    build: HaystackBuild,
    *,
    chunk_size_tokens: int = 256,
    document_title: str = "needle-haystack",
) -> tuple[str, list[str], int | None]:
    """Ingest haystack chunks into OpenViking (L0/L1/L2 tiers)."""
    chunks = chunk_text(build.text, chunk_size_tokens)
    needle_index = find_needle_chunk_index(chunks, build.needle.needle_text)
    now = datetime.utcnow()
    doc = Document(
        title=document_title,
        source="needle_benchmark",
        metadata={
            "depth_percent": build.depth_percent,
            "actual_depth_percent": build.placement.actual_depth_percent,
            "token_count": build.token_count,
        },
        created_at=now,
    )
    document_chunks: list[DocumentChunk] = []
    for index, content in enumerate(chunks):
        document_chunks.extend(
            [
                DocumentChunk(
                    level=0,
                    content=_summary(content, 80),
                    metadata={"chunk_index": index, "tier": "summary"},
                    created_at=now,
                ),
                DocumentChunk(
                    level=1,
                    content=_summary(content, 200),
                    metadata={"chunk_index": index, "tier": "section"},
                    created_at=now,
                ),
                DocumentChunk(
                    level=2,
                    content=content,
                    metadata={"chunk_index": index, "tier": "detail"},
                    created_at=now,
                ),
            ]
        )
    document_id = await vector.ingest_document(doc, document_chunks)
    return document_id, chunks, needle_index


async def ingest_haystack_episodic(
    episodic: EpisodicMemoryStore,
    build: HaystackBuild,
    *,
    chunk_size_tokens: int = 256,
) -> tuple[list[str], int | None]:
    """Store haystack segments as episodic memories (Mnemosyne tier)."""
    chunks = chunk_text(build.text, chunk_size_tokens)
    needle_index = find_needle_chunk_index(chunks, build.needle.needle_text)
    for index, content in enumerate(chunks):
        await episodic.store_episode(
            Episode(
                content=content,
                episode_type="haystack_segment",
                confidence=0.7,
                metadata={
                    "chunk_index": index,
                    "depth_percent": build.depth_percent,
                    "token_count": count(content),
                    "benchmark": "needle_in_haystack",
                },
            )
        )
    return chunks, needle_index

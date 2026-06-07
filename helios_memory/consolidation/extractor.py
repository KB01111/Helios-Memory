"""Rule-based memory candidate extraction from conversation turns."""

from __future__ import annotations

import re
from datetime import datetime

from helios_memory.models import MemoryCandidate

_CORRECTION_PATTERNS = [
    re.compile(r"(?i)\b(actually|correction|i meant|not .+ but)\b"),
    re.compile(r"(?i)\b(that(?:'s| is) (?:wrong|incorrect))\b"),
]

_PREFERENCE_PATTERNS = [
    re.compile(r"(?i)\b(i prefer|i like|i love|i hate|i don'?t like)\b"),
    re.compile(r"(?i)\b(my favorite|my preferred)\b"),
]

_PROJECT_STATE_PATTERNS = [
    re.compile(r"(?i)\b(the project|this repo|the codebase|we(?:'re| are) using)\b"),
    re.compile(r"(?i)\b(currently|now we|architecture is)\b"),
]

_FACT_PATTERNS = [
    re.compile(r"(?i)\b(is|are|was|were|has|have)\b"),
    re.compile(r"(?i)\b(always|never|usually)\b"),
]


def _classify_memory_type(text: str) -> str:
    for pattern in _CORRECTION_PATTERNS:
        if pattern.search(text):
            return "correction"
    for pattern in _PREFERENCE_PATTERNS:
        if pattern.search(text):
            return "preference"
    for pattern in _PROJECT_STATE_PATTERNS:
        if pattern.search(text):
            return "project_state"
    for pattern in _FACT_PATTERNS:
        if pattern.search(text):
            return "fact"
    return "episode"


def _confidence_for_type(memory_type: str) -> float:
    return {
        "correction": 0.9,
        "preference": 0.85,
        "project_state": 0.75,
        "fact": 0.7,
        "episode": 0.6,
    }.get(memory_type, 0.5)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _extract_topic_key(content: str) -> str | None:
    """Derive a coarse topic key for conflict detection."""
    lowered = content.lower()
    for prefix in ("prefer", "favorite", "like", "dislike", "use", "name is"):
        match = re.search(rf"(?i)\b{prefix}\b\s+(.{{3,40}})", lowered)
        if match:
            return f"{prefix}:{match.group(1).split()[0]}"
    words = re.findall(r"[a-z0-9_]{4,}", lowered)
    if words:
        return words[0]
    return None


def extract_candidates(
    user_prompt: str,
    assistant_response: str,
    *,
    source: str = "consolidation",
) -> list[MemoryCandidate]:
    """Extract memory candidates using rule-based sentence patterns."""
    candidates: list[MemoryCandidate] = []
    now = datetime.utcnow()

    for role, text in (("user", user_prompt), ("assistant", assistant_response)):
        for sentence in _split_sentences(text):
            if len(sentence) < 12:
                continue

            memory_type = _classify_memory_type(sentence)
            topic_key = _extract_topic_key(sentence)

            candidates.append(
                MemoryCandidate(
                    content=sentence,
                    memory_type=memory_type,
                    confidence=_confidence_for_type(memory_type),
                    source=source,
                    tags=[role, memory_type],
                    metadata={
                        "role": role,
                        "topic_key": topic_key,
                        "explicit_correction": memory_type == "correction",
                    },
                    created_at=now,
                )
            )

    return candidates

"""Reasoning model protocol (OpenAI-compatible)."""

from __future__ import annotations

from typing import Protocol

from helios_memory.models import MemoryBrief


class ReasoningModel(Protocol):
    """Generates the final assistant response from prompt + memory brief."""

    async def generate(
        self,
        prompt: str,
        brief: MemoryBrief,
        session_id: str,
    ) -> str: ...

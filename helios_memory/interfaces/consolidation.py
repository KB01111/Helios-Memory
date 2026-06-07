"""Post-response consolidation protocol."""

from __future__ import annotations

from typing import Protocol

from helios_memory.models import ConsolidationResult, Intent


class ConsolidationWorker(Protocol):
    """Extracts and persists memories after the user-facing response."""

    async def consolidate(
        self,
        session_id: str,
        user_prompt: str,
        assistant_response: str,
        intent: Intent,
    ) -> ConsolidationResult: ...

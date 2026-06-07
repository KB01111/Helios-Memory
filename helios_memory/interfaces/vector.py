"""OpenViking vector archive protocol (semantic tier)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from helios_memory.models import TieredRetrieval

if TYPE_CHECKING:
    from helios_memory.models.storage import Document, DocumentChunk


class VectorArchive(Protocol):
    """Semantic archive with L0/L1/L2 tiered retrieval."""

    async def ingest_document(
        self,
        doc: Document,
        chunks: list[DocumentChunk],
    ) -> str: ...

    async def retrieve_tiered(
        self,
        query: str,
        levels: list[int] | None = None,
    ) -> TieredRetrieval: ...

    async def search_metadata(
        self,
        filters: dict[str, Any],
    ) -> list[DocumentChunk]: ...

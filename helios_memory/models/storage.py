"""Storage-tier Pydantic models (stub until providers-worker extends)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CacheEntry(BaseModel):
    """Holographic cache record."""

    key: str = ""
    content: str
    ttl: int | None = None
    recency: float = 1.0
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    tags: list[str] = Field(default_factory=list)
    source: str = "unknown"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Episode(BaseModel):
    """Mnemosyne episodic memory record."""

    id: str = ""
    content: str
    episode_type: str = "episode"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    corrected_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    """Archive document metadata."""

    id: str = ""
    title: str = ""
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentChunk(BaseModel):
    """Single tiered chunk within an archive document."""

    id: str = ""
    document_id: str = ""
    level: int = 0
    content: str
    embedding: bytes | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MemoryEvent(BaseModel):
    """Audit log entry for memory mutations."""

    id: str = ""
    memory_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str = "system"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Conflict(BaseModel):
    """Detected contradiction between memories."""

    id: str = ""
    memory_id_a: str
    memory_id_b: str
    conflict_type: str = "contradiction"
    status: str = "detected"
    resolution: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None


class ConflictResolution(BaseModel):
    """Resolution action for a memory conflict."""

    winning_memory_id: str
    losing_memory_id: str
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

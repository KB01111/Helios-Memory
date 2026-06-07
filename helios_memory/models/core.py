"""Shared Pydantic models for the Helios Memory plugin."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IntentCategory(str, Enum):
    """Categories returned by the intent router."""

    SMALL_TALK = "small_talk"
    TASK_REQUEST = "task_request"
    MEMORY_LOOKUP_NEEDED = "memory_lookup_needed"
    PROJECT_CONTEXT_NEEDED = "project_context_needed"
    SENSITIVE_REQUEST = "sensitive_request"


class Intent(BaseModel):
    """Classified user intent with retrieval hints."""

    category: IntentCategory
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    requires_memory: bool = False
    requires_archive: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryCandidate(BaseModel):
    """A candidate memory extracted during consolidation."""

    content: str
    memory_type: str = "fact"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    source: str = "consolidation"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MemoryBrief(BaseModel):
    """Compact synthesized context injected into the reasoning model."""

    summary: str
    cache_hits: int = 0
    episode_count: int = 0
    archive_chunks: int = 0
    token_estimate: int = 0
    sources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataClassification(str, Enum):
    """Sensitivity level for content sent to cloud providers."""

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class PrivacyPolicy(BaseModel):
    """User-configurable privacy rules for cloud-bound data."""

    allow_cloud_inference: bool = True
    allow_raw_file_upload: bool = False
    redact_sensitive: bool = True
    block_sensitive_by_default: bool = True
    allowed_classifications_for_cloud: list[DataClassification] = Field(
        default_factory=lambda: [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
        ]
    )


class TieredRetrieval(BaseModel):
    """Tiered archive retrieval result (L0/L1/L2)."""

    level_0: list[dict[str, Any]] = Field(default_factory=list)
    level_1: list[dict[str, Any]] = Field(default_factory=list)
    level_2: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return len(self.level_0) + len(self.level_1) + len(self.level_2)


class ConsolidationResult(BaseModel):
    """Outcome of post-response memory consolidation."""

    candidates_stored: int = 0
    conflicts_detected: int = 0
    decay_applied: int = 0
    audit_events: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

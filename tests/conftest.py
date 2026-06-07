"""Shared pytest fixtures for Helios Memory tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from helios_memory.config import HeliosConfig, HeliosMode
from helios_memory.interfaces import ReasoningModel
from helios_memory.models import Intent, IntentCategory, MemoryBrief
from helios_memory.providers.sqlite import (
    SQLiteCacheStore,
    SQLiteEpisodicStore,
    SQLiteVectorArchive,
)
from helios_memory.routing.rules import RoutingRules, load_routing_rules


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    """Temporary SQLite database path."""
    return str(tmp_path / "helios_test.db")


@pytest.fixture
def sample_config(tmp_db: str) -> HeliosConfig:
    """HeliosConfig configured for local in-memory SQLite."""
    return HeliosConfig(
        mode=HeliosMode.LOCAL,
        storage={"sqlite_path": tmp_db},
        consolidation_enabled=True,
    )


@pytest.fixture
async def local_stores(
    sample_config: HeliosConfig,
) -> AsyncGenerator[
    tuple[SQLiteCacheStore, SQLiteEpisodicStore, SQLiteVectorArchive],
    None,
]:
    """Connected local SQLite cache, episodic, and vector stores."""
    db_path = sample_config.storage.sqlite_path
    cache = SQLiteCacheStore(db_path)
    episodic = SQLiteEpisodicStore(db_path)
    vector = SQLiteVectorArchive(db_path)
    await cache.connect()
    await episodic.connect()
    await vector.connect()
    yield cache, episodic, vector
    await cache.close()
    await episodic.close()
    await vector.close()


@pytest.fixture
def routing_rules() -> RoutingRules:
    """Routing rules loaded from project config."""
    config_path = Path(__file__).resolve().parents[1] / "config" / "routing_rules.yaml"
    return load_routing_rules(config_path)


@pytest.fixture
def mock_reasoning_model() -> ReasoningModel:
    """Deterministic reasoning model stub for integration tests."""

    class _MockReasoningModel:
        async def reason(
            self,
            prompt: str,
            memory_brief: MemoryBrief,
            **kwargs: Any,
        ) -> str:
            _ = kwargs
            return f"Mock response for: {prompt[:80]} (brief tokens={memory_brief.token_estimate})"

        async def classify_intent(self, prompt: str) -> Intent:
            return Intent(
                category=IntentCategory.TASK_REQUEST,
                confidence=0.7,
                metadata={"match": "mock_llm"},
            )

    return _MockReasoningModel()  # type: ignore[return-value]


@pytest.fixture
def frozen_now() -> datetime:
    """Fixed timestamp for deterministic decay tests."""
    return datetime(2025, 6, 7, 12, 0, 0)

"""Factory helpers for local, cloud, and hybrid memory stores and reasoning models."""

from __future__ import annotations

from pathlib import Path

from helios_memory.config import HeliosConfig, HeliosMode
from helios_memory.consolidation import ConsolidationWorker
from helios_memory.interfaces import (
    CacheStore,
    ConsolidationWorker as ConsolidationWorkerProtocol,
    EpisodicMemoryStore,
    IntentRouter,
    MemorySynthesizer as MemorySynthesizerProtocol,
    ReasoningModel,
    VectorArchive,
)
from helios_memory.routing import (
    MemorySynthesizer,
    RuleBasedIntentRouter,
    load_routing_rules,
)
from helios_memory.providers.cloud import (
    CloudReasoningProvider,
    SupabaseEpisodicStore,
    SupabaseVectorArchive,
    UpstashRedisCacheStore,
)
from helios_memory.providers.fastflowlm import FastFlowLMProvider
from helios_memory.providers.ollama import OllamaProvider
from helios_memory.providers.sqlite import (
    SQLiteCacheStore,
    SQLiteEpisodicStore,
    SQLiteVectorArchive,
)


async def create_local_stores(
    config: HeliosConfig,
) -> tuple[CacheStore, EpisodicMemoryStore, VectorArchive]:
    """Create and connect all three local SQLite memory tiers."""
    db_path = config.storage.sqlite_path
    cache = SQLiteCacheStore(db_path)
    episodic = SQLiteEpisodicStore(db_path)
    vector = SQLiteVectorArchive(db_path)
    await cache.connect()
    await episodic.connect()
    await vector.connect()
    return cache, episodic, vector


async def create_cloud_stores(
    config: HeliosConfig,
) -> tuple[CacheStore, EpisodicMemoryStore, VectorArchive]:
    """Create and connect cloud-backed memory tiers (Upstash + Supabase)."""
    cache = UpstashRedisCacheStore()
    episodic = SupabaseEpisodicStore()
    vector = SupabaseVectorArchive()
    await cache.connect()
    await episodic.connect()
    await vector.connect()
    return cache, episodic, vector


async def create_hybrid_stores(
    config: HeliosConfig,
) -> tuple[CacheStore, EpisodicMemoryStore, VectorArchive]:
    """Create hybrid stores: local SQLite cache + cloud episodic and vector tiers."""
    db_path = config.storage.sqlite_path
    cache = SQLiteCacheStore(db_path)
    episodic = SupabaseEpisodicStore()
    vector = SupabaseVectorArchive()
    await cache.connect()
    await episodic.connect()
    await vector.connect()
    return cache, episodic, vector


def create_reasoning_model(
    config: HeliosConfig,
    *,
    use_ollama_fallback: bool = True,
) -> ReasoningModel:
    """Select a reasoning provider based on deployment mode.

    - ``local`` / ``hybrid``: FastFlowLM with optional Ollama fallback.
    - ``cloud``: OpenAI-compatible cloud provider with privacy enforcement.
    """
    if config.mode == HeliosMode.CLOUD:
        return CloudReasoningProvider(privacy_policy=config.privacy)

    ollama: OllamaProvider | None = None
    if use_ollama_fallback:
        ollama = OllamaProvider(
            base_url=config.providers.ollama_url,
            model=config.models.ollama_model,
            privacy_policy=config.privacy,
        )

    return FastFlowLMProvider(
        base_url=config.providers.fastflowlm_url,
        model=config.models.reasoning_model,
        privacy_policy=config.privacy,
        fallback=ollama,
    )


def create_intent_router(
    config: HeliosConfig | None = None,
    rules_path: str | Path | None = None,
) -> IntentRouter:
    """Create rule-based intent router from config routing rules YAML."""
    _ = config
    rules = load_routing_rules(rules_path)
    return RuleBasedIntentRouter(rules=rules)


def create_memory_synthesizer(config: HeliosConfig) -> MemorySynthesizerProtocol:
    """Create template-based memory synthesizer with configured token budget."""
    return MemorySynthesizer(max_tokens=config.memory_brief_max_tokens)


def create_consolidation_worker(
    store: EpisodicMemoryStore,
) -> ConsolidationWorkerProtocol:
    """Create post-response consolidation worker bound to episodic store."""
    return ConsolidationWorker(store=store)

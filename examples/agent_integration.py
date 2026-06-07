"""Minimal Helios Memory plugin bootstrap for agent integration."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from repo root: python examples/agent_integration.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helios_memory.config import HeliosConfig, HeliosMode
from helios_memory.plugin import HeliosMemoryPlugin
from helios_memory.privacy import PrivacyEnforcer
from helios_memory.providers.factory import (
    create_cloud_stores,
    create_consolidation_worker,
    create_hybrid_stores,
    create_intent_router,
    create_local_stores,
    create_memory_synthesizer,
    create_reasoning_model,
)


async def build_plugin(config: HeliosConfig) -> HeliosMemoryPlugin:
    """Wire stores and routing factories into a HeliosMemoryPlugin."""
    if config.mode == HeliosMode.LOCAL:
        cache, episodic, vector = await create_local_stores(config)
    elif config.mode == HeliosMode.CLOUD:
        cache, episodic, vector = await create_cloud_stores(config)
    else:
        cache, episodic, vector = await create_hybrid_stores(config)

    return HeliosMemoryPlugin(
        config=config,
        cache_store=cache,
        episodic_store=episodic,
        vector_archive=vector,
        intent_router=create_intent_router(config),
        synthesizer=create_memory_synthesizer(config),
        reasoning_model=create_reasoning_model(config),
        consolidation_worker=create_consolidation_worker(episodic),
        privacy=PrivacyEnforcer(config.privacy),
    )


async def main() -> None:
    config_path = Path("config/local.yaml")
    if not config_path.exists():
        config_path = Path("config/local.yaml.example")
    config = HeliosConfig.load(config_path)

    plugin = await build_plugin(config)
    response = await plugin.process(
        "What did we decide about the API design?",
        session_id="demo",
    )
    print(response)


if __name__ == "__main__":
    asyncio.run(main())

"""Example: wrap Helios Memory in a simple async agent loop (Hermes-like hook)."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helios_memory.config import HeliosConfig
from helios_memory.plugin import HeliosMemoryPlugin
from helios_memory.privacy import PrivacyEnforcer
from helios_memory.providers.factory import (
    create_consolidation_worker,
    create_intent_router,
    create_local_stores,
    create_memory_synthesizer,
    create_reasoning_model,
)


async def build_plugin(config: HeliosConfig) -> HeliosMemoryPlugin:
    cache, episodic, vector = await create_local_stores(config)
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


@dataclass
class SimpleAgent:
    """Minimal agent that delegates memory-augmented turns to HeliosMemoryPlugin."""

    plugin: HeliosMemoryPlugin
    session_id: str = "agent-session"
    history: list[tuple[str, str]] = field(default_factory=list)

    async def handle_user_message(self, user_prompt: str) -> str:
        """Process one user turn through Helios Memory and record history."""
        response = await self.plugin.process(user_prompt, session_id=self.session_id)
        self.history.append((user_prompt, response))
        return response

    async def run_loop(self, prompts: list[str]) -> None:
        for prompt in prompts:
            print(f"User: {prompt}")
            reply = await self.handle_user_message(prompt)
            print(f"Agent: {reply}\n")


async def main() -> None:
    config = HeliosConfig.load("config/local.yaml.example")
    plugin = await build_plugin(config)
    agent = SimpleAgent(plugin=plugin, session_id="hermes-demo")

    await agent.run_loop(
        [
            "Hello!",
            "Remember that we chose REST over GraphQL for the public API.",
            "What did we decide about the API design?",
        ]
    )


if __name__ == "__main__":
    asyncio.run(main())

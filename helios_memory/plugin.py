"""Main plugin entrypoint for Helios Memory."""

from __future__ import annotations

from helios_memory.config import HeliosConfig
from helios_memory.interfaces import (
    CacheStore,
    ConsolidationWorker,
    EpisodicMemoryStore,
    IntentRouter,
    MemorySynthesizer,
    ReasoningModel,
    VectorArchive,
)
from helios_memory.privacy import PrivacyEnforcer
from helios_memory.workflow import MemoryWorkflow


class HeliosMemoryPlugin:
    """Provider-agnostic memory plugin with constructor dependency injection."""

    def __init__(
        self,
        config: HeliosConfig,
        cache_store: CacheStore,
        episodic_store: EpisodicMemoryStore,
        vector_archive: VectorArchive,
        intent_router: IntentRouter,
        synthesizer: MemorySynthesizer,
        reasoning_model: ReasoningModel,
        consolidation_worker: ConsolidationWorker,
        privacy: PrivacyEnforcer | None = None,
    ) -> None:
        self.config = config
        self._workflow = MemoryWorkflow(
            config=config,
            cache_store=cache_store,
            episodic_store=episodic_store,
            vector_archive=vector_archive,
            intent_router=intent_router,
            synthesizer=synthesizer,
            reasoning_model=reasoning_model,
            consolidation_worker=consolidation_worker,
            privacy=privacy,
        )

    async def process(self, user_prompt: str, session_id: str) -> str:
        """Process a user prompt through the memory-augmented pipeline."""
        return await self._workflow.run(user_prompt, session_id)

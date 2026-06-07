"""Post-response memory consolidation."""

from helios_memory.consolidation.conflict_resolver import (
    ConflictResolver,
    detect_conflict,
)
from helios_memory.consolidation.decay import DecayConfig, compute_decay_factor
from helios_memory.consolidation.extractor import extract_candidates
from helios_memory.consolidation.worker import ConsolidationWorker

__all__ = [
    "ConflictResolver",
    "ConsolidationWorker",
    "DecayConfig",
    "compute_decay_factor",
    "detect_conflict",
    "extract_candidates",
]

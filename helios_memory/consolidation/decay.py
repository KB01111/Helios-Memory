"""Temporal confidence decay utilities."""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, Field


class DecayConfig(BaseModel):
    """Configurable decay parameters per memory type."""

    mode: str = "exponential"  # exponential | linear
    default_half_life_days: float = 30.0
    half_life_days: dict[str, float] = Field(
        default_factory=lambda: {
            "fact": 60.0,
            "preference": 90.0,
            "project_state": 45.0,
            "correction": 120.0,
            "episode": 14.0,
        }
    )

    def half_life_for(self, memory_type: str) -> float:
        return self.half_life_days.get(memory_type, self.default_half_life_days)


def compute_decay_factor(
    created_at: datetime,
    memory_type: str,
    config: DecayConfig,
    as_of: datetime | None = None,
) -> float:
    """Compute decay multiplier in (0, 1] for a memory age and type."""
    reference = as_of or datetime.utcnow()
    age_seconds = max(0.0, (reference - created_at).total_seconds())
    age_days = age_seconds / 86400.0
    half_life = max(config.half_life_for(memory_type), 0.001)

    if config.mode == "linear":
        # Reaches ~0 at 2 * half-life.
        factor = 1.0 - (age_days / (2.0 * half_life))
        return max(0.0, min(1.0, factor))

    # Exponential half-life decay.
    return max(0.0, min(1.0, math.pow(0.5, age_days / half_life)))

"""Configuration loading for Helios Memory (YAML + HELIOS_* env vars)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from helios_memory.models import PrivacyPolicy


class HeliosMode(str, Enum):
    """Deployment mode controlling provider selection."""

    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class ModelConfig(BaseModel):
    """LLM model names for routing, synthesis, and reasoning."""

    routing_model: str = "gemma4-it:e2b"
    synthesis_model: str = "gemma4-it:e4b"
    reasoning_model: str = "gemma4-it:e4b"
    ollama_model: str = "gemma4:12b"


class ProviderEndpoints(BaseModel):
    """OpenAI-compatible provider base URLs."""

    fastflowlm_url: str = "http://127.0.0.1:52625/v1"
    ollama_url: str = "http://127.0.0.1:11434/v1"


class StorageConfig(BaseModel):
    """Local storage paths."""

    sqlite_path: str = "helios_memory.db"


class HeliosConfig(BaseSettings):
    """Top-level plugin configuration.

    Environment variables use the ``HELIOS_`` prefix, e.g. ``HELIOS_MODE=local``.
    Nested keys use double underscores: ``HELIOS_MODELS__ROUTING_MODEL``.
    """

    model_config = SettingsConfigDict(
        env_prefix="HELIOS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    mode: HeliosMode = HeliosMode.LOCAL
    providers: ProviderEndpoints = Field(default_factory=ProviderEndpoints)
    models: ModelConfig = Field(default_factory=ModelConfig)
    privacy: PrivacyPolicy = Field(default_factory=PrivacyPolicy)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    memory_brief_max_tokens: int = 2000
    consolidation_enabled: bool = True

    @classmethod
    def from_yaml(cls, path: str | Path) -> HeliosConfig:
        """Load configuration from a YAML file, with env vars overriding values."""
        config_path = Path(path)
        data: dict[str, Any] = {}
        if config_path.exists():
            with config_path.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle)
                if isinstance(loaded, dict):
                    data = loaded
        return cls(**data)

    @classmethod
    def load(cls, yaml_path: str | Path | None = None) -> HeliosConfig:
        """Load from optional YAML file; env vars always take precedence."""
        if yaml_path is None:
            return cls()
        return cls.from_yaml(yaml_path)

    @property
    def fastflowlm_url(self) -> str:
        return self.providers.fastflowlm_url

    @property
    def is_local(self) -> bool:
        return self.mode in (HeliosMode.LOCAL, HeliosMode.HYBRID)

    @property
    def is_cloud(self) -> bool:
        return self.mode in (HeliosMode.CLOUD, HeliosMode.HYBRID)

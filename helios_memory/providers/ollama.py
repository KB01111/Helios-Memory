"""Ollama OpenAI-compatible reasoning provider (local fallback)."""

from __future__ import annotations

import logging
import os

from openai import APIConnectionError, AsyncOpenAI, OpenAIError

from helios_memory.models import MemoryBrief, PrivacyPolicy

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "gemma4:12b"


class OllamaUnavailableError(RuntimeError):
    """Raised when Ollama cannot be reached."""


class OllamaProvider:
    """OpenAI-compatible client for local Ollama inference.

    Implements ``ReasoningModel`` via ``generate()``.

    Environment:
        ``HELIOS_OLLAMA_BASE_URL`` — overrides the configured base URL.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
        privacy_policy: PrivacyPolicy | None = None,
        *,
        api_key: str = "ollama",
    ) -> None:
        resolved_url = (
            base_url
            or os.environ.get("HELIOS_OLLAMA_BASE_URL")
            or DEFAULT_BASE_URL
        )
        self._base_url = resolved_url.rstrip("/")
        self._model = model
        self._privacy_policy = privacy_policy or PrivacyPolicy()
        self._client = AsyncOpenAI(base_url=self._base_url, api_key=api_key)

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    async def is_available(self) -> bool:
        """Return whether the Ollama endpoint responds."""
        try:
            await self._client.models.list()
            return True
        except (APIConnectionError, OpenAIError):
            return False

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> str:
        """Low-level chat completion against Ollama."""
        model = str(kwargs.pop("model", self._model))
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                **kwargs,  # type: ignore[arg-type]
            )
        except APIConnectionError as exc:
            raise OllamaUnavailableError(
                f"Ollama unavailable at {self._base_url}. "
                "Ensure Ollama is running with the OpenAI-compatible API enabled."
            ) from exc
        except OpenAIError as exc:
            raise OllamaUnavailableError(f"Ollama request failed: {exc}") from exc

        content = response.choices[0].message.content
        return content or ""

    async def generate(
        self,
        prompt: str,
        brief: MemoryBrief,
        session_id: str,
    ) -> str:
        """Generate a response from the user prompt and memory brief."""
        system_parts = ["You are a helpful assistant with access to memory context."]
        if brief.summary.strip():
            system_parts.append(f"Memory brief:\n{brief.summary}")
        if brief.sources:
            system_parts.append(f"Sources: {', '.join(brief.sources)}")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {"role": "user", "content": prompt},
        ]
        logger.debug(
            "Ollama generate session=%s model=%s brief_tokens=%s",
            session_id,
            self._model,
            brief.token_estimate,
        )
        return await self.complete(messages)

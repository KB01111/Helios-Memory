"""Cloud OpenAI/Anthropic-compatible reasoning provider with privacy checks."""

from __future__ import annotations

import logging
import os

from openai import APIConnectionError, AsyncOpenAI, OpenAIError

from helios_memory.models import MemoryBrief, PrivacyPolicy
from helios_memory.privacy import PrivacyEnforcer

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class CloudReasoningBlockedError(RuntimeError):
    """Raised when privacy policy blocks a cloud reasoning request."""


class CloudReasoningProvider:
    """OpenAI-compatible cloud LLM for heavy reasoning.

    Implements ``ReasoningModel`` via ``generate()``.

    All outbound content is checked through ``PrivacyEnforcer`` before each call.

    Environment:
        ``HELIOS_CLOUD_API_KEY`` — API key (required for real calls).
        ``HELIOS_CLOUD_BASE_URL`` — OpenAI-compatible base URL.
        ``HELIOS_CLOUD_MODEL`` — model name override.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("HELIOS_CLOUD_API_KEY", "")
        self._base_url = (
            base_url or os.environ.get("HELIOS_CLOUD_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self._model = model or os.environ.get("HELIOS_CLOUD_MODEL") or DEFAULT_MODEL
        self._privacy_policy = privacy_policy or PrivacyPolicy()
        self._enforcer = PrivacyEnforcer(self._privacy_policy)
        self._client: AsyncOpenAI | None = None

    @property
    def model(self) -> str:
        return self._model

    def _client_or_raise(self) -> AsyncOpenAI:
        if not self._api_key:
            raise RuntimeError(
                "HELIOS_CLOUD_API_KEY is not set; cloud reasoning is unavailable."
            )
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    def _check_privacy(self, content: str) -> str:
        """Enforce privacy policy; return sanitized content or raise."""
        decision = self._enforcer.enforce_before_cloud(content)
        if not decision.allowed:
            raise CloudReasoningBlockedError(
                decision.blocked_reason or "Cloud transmission blocked by privacy policy."
            )
        return decision.content

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> str:
        """Low-level chat completion with privacy checks on all message content."""
        sanitized: list[dict[str, str]] = []
        for message in messages:
            content = self._check_privacy(message.get("content", ""))
            sanitized.append({**message, "content": content})

        model = str(kwargs.pop("model", self._model))
        client = self._client_or_raise()
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=sanitized,  # type: ignore[arg-type]
                **kwargs,  # type: ignore[arg-type]
            )
        except APIConnectionError as exc:
            raise RuntimeError(
                f"Cloud reasoning provider unavailable at {self._base_url}: {exc}"
            ) from exc
        except OpenAIError as exc:
            raise RuntimeError(f"Cloud reasoning request failed: {exc}") from exc

        content = response.choices[0].message.content
        return content or ""

    async def generate(
        self,
        prompt: str,
        brief: MemoryBrief,
        session_id: str,
    ) -> str:
        """Generate a response with privacy enforcement on prompt and brief."""
        safe_prompt = self._check_privacy(prompt)
        safe_brief = self._check_privacy(brief.summary) if brief.summary else ""

        system_parts = ["You are a helpful assistant with access to memory context."]
        if safe_brief.strip():
            system_parts.append(f"Memory brief:\n{safe_brief}")
        if brief.sources:
            system_parts.append(f"Sources: {', '.join(brief.sources)}")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {"role": "user", "content": safe_prompt},
        ]
        logger.debug(
            "CloudReasoning generate session=%s model=%s",
            session_id,
            self._model,
        )
        return await self.complete(messages)

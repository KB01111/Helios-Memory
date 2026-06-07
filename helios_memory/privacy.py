"""Privacy policy enforcement before cloud-bound API calls."""

from __future__ import annotations

import re
from dataclasses import dataclass

from helios_memory.models import DataClassification, PrivacyPolicy


@dataclass(frozen=True)
class PrivacyDecision:
    """Result of a privacy enforcement check."""

    allowed: bool
    classification: DataClassification
    content: str
    blocked_reason: str | None = None


# Patterns for heuristic content classification.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|secret[_-]?key|password|passwd|token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"(?i)ghp_[a-zA-Z0-9]{20,}"),
)

_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-like
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),  # email
    re.compile(r"(?i)\b(credit\s*card|ssn|social\s*security|passport)\b"),
    re.compile(r"(?i)\b(\.env|credentials\.json|id_rsa|\.pem)\b"),
)

_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)((?:api[_-]?key|secret|password|token)\s*[:=]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED-SSN]"),
    (
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "[REDACTED-EMAIL]",
    ),
)


class PrivacyEnforcer:
    """Classifies content and enforces privacy policy before cloud calls."""

    def __init__(self, policy: PrivacyPolicy | None = None) -> None:
        self.policy = policy or PrivacyPolicy()

    def classify_content(self, content: str) -> DataClassification:
        """Heuristically classify content sensitivity."""
        if not content.strip():
            return DataClassification.PUBLIC

        for pattern in _SECRET_PATTERNS:
            if pattern.search(content):
                return DataClassification.SECRET

        for pattern in _SENSITIVE_PATTERNS:
            if pattern.search(content):
                return DataClassification.SENSITIVE

        if len(content) > 500 and any(
            marker in content.lower()
            for marker in ("confidential", "internal only", "do not share")
        ):
            return DataClassification.INTERNAL

        return DataClassification.PUBLIC

    def redact(self, content: str) -> str:
        """Redact known sensitive patterns from content."""
        redacted = content
        for pattern, replacement in _REDACT_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    def requires_upload_opt_in(self) -> bool:
        """Raw file uploads to cloud require explicit user opt-in."""
        return not self.policy.allow_raw_file_upload

    def can_send_to_cloud(
        self,
        content: str,
        classification: DataClassification | None = None,
    ) -> bool:
        """Return whether content may be sent to a cloud provider."""
        if not self.policy.allow_cloud_inference:
            return False

        level = classification or self.classify_content(content)

        if level == DataClassification.SECRET:
            return False

        if level == DataClassification.SENSITIVE and self.policy.block_sensitive_by_default:
            return False

        return level in self.policy.allowed_classifications_for_cloud

    def enforce_before_cloud(
        self,
        content: str,
        *,
        is_raw_file: bool = False,
    ) -> PrivacyDecision:
        """Classify, redact, and decide whether cloud transmission is allowed."""
        classification = self.classify_content(content)

        if is_raw_file and self.requires_upload_opt_in():
            return PrivacyDecision(
                allowed=False,
                classification=classification,
                content=content,
                blocked_reason="Raw file upload to cloud requires explicit opt-in.",
            )

        processed = content
        if self.policy.redact_sensitive and classification in (
            DataClassification.SENSITIVE,
            DataClassification.SECRET,
        ):
            processed = self.redact(content)

        if not self.can_send_to_cloud(content, classification):
            reason = "Content classification blocks cloud transmission."
            if classification == DataClassification.SECRET:
                reason = "Secret content cannot be sent to cloud providers."
            elif classification == DataClassification.SENSITIVE:
                reason = "Sensitive content is blocked by default."
            return PrivacyDecision(
                allowed=False,
                classification=classification,
                content=processed,
                blocked_reason=reason,
            )

        return PrivacyDecision(
            allowed=True,
            classification=classification,
            content=processed,
        )

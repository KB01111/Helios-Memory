"""Routing rule definitions and YAML loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from helios_memory.models import IntentCategory


class CategoryRules(BaseModel):
    """Patterns and retrieval hints for a single intent category."""

    keywords: list[str] = Field(default_factory=list)
    regex: list[str] = Field(default_factory=list)
    requires_memory: bool = False
    requires_archive: bool = False


class ConfidenceRules(BaseModel):
    """Confidence scores assigned by match type."""

    keyword_match: float = 0.85
    regex_match: float = 0.9
    multiple_matches: float = 0.95
    default_task: float = 0.6
    llm_fallback: float = 0.7


class RoutingRules(BaseModel):
    """Full routing configuration loaded from YAML."""

    priority: list[str] = Field(
        default_factory=lambda: [
            "sensitive_request",
            "memory_lookup_needed",
            "project_context_needed",
            "small_talk",
            "task_request",
        ]
    )
    confidence: ConfidenceRules = Field(default_factory=ConfidenceRules)
    ambiguous_threshold: float = 0.5
    categories: dict[str, CategoryRules] = Field(default_factory=dict)

    def category_rules(self, category: IntentCategory | str) -> CategoryRules:
        """Return rules for a category, or empty defaults."""
        key = category.value if isinstance(category, IntentCategory) else category
        return self.categories.get(key, CategoryRules())

    def priority_categories(self) -> list[IntentCategory]:
        """Resolve priority list to IntentCategory values, skipping unknown keys."""
        result: list[IntentCategory] = []
        for name in self.priority:
            try:
                result.append(IntentCategory(name))
            except ValueError:
                continue
        return result


def _parse_categories(raw: dict[str, Any]) -> dict[str, CategoryRules]:
    categories: dict[str, CategoryRules] = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        categories[name] = CategoryRules(
            keywords=[str(k).lower() for k in spec.get("keywords", [])],
            regex=[str(p) for p in spec.get("regex", [])],
            requires_memory=bool(spec.get("requires_memory", False)),
            requires_archive=bool(spec.get("requires_archive", False)),
        )
    return categories


def load_routing_rules(path: str | Path | None = None) -> RoutingRules:
    """Load routing rules from YAML; falls back to built-in defaults."""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "config" / "routing_rules.yaml"

    config_path = Path(path)
    if not config_path.exists():
        return RoutingRules()

    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        return RoutingRules()

    confidence_raw = data.get("confidence", {})
    confidence = (
        ConfidenceRules(**confidence_raw)
        if isinstance(confidence_raw, dict)
        else ConfidenceRules()
    )

    categories_raw = data.get("categories", {})
    categories = (
        _parse_categories(categories_raw)
        if isinstance(categories_raw, dict)
        else {}
    )

    priority = data.get("priority")
    if not isinstance(priority, list):
        priority = [
            "sensitive_request",
            "memory_lookup_needed",
            "project_context_needed",
            "small_talk",
            "task_request",
        ]

    return RoutingRules(
        priority=[str(item) for item in priority],
        confidence=confidence,
        ambiguous_threshold=float(data.get("ambiguous_threshold", 0.5)),
        categories=categories,
    )

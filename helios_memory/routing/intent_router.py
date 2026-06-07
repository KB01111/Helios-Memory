"""Rule-based intent classification with optional LLM fallback."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from helios_memory.models import Intent, IntentCategory
from helios_memory.routing.rules import CategoryRules, RoutingRules, load_routing_rules

logger = logging.getLogger(__name__)

LLMClassifyFn = Callable[[str], Awaitable[Intent | None]]


def _count_keyword_matches(prompt_lower: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in prompt_lower)


def _count_regex_matches(prompt: str, patterns: list[str]) -> int:
    count = 0
    for pattern in patterns:
        try:
            if re.search(pattern, prompt):
                count += 1
        except re.error:
            logger.warning("Invalid routing regex skipped: %s", pattern)
    return count


def _score_category(
    prompt: str,
    prompt_lower: str,
    rules: CategoryRules,
) -> tuple[int, int]:
    """Return (keyword_hits, regex_hits) for a category."""
    keyword_hits = _count_keyword_matches(prompt_lower, rules.keywords)
    regex_hits = _count_regex_matches(prompt, rules.regex)
    return keyword_hits, regex_hits


def classify_with_rules(prompt: str, rules: RoutingRules) -> Intent:
    """Pure rule-based intent classification (unit-testable without LLM)."""
    prompt_lower = prompt.lower().strip()
    if not prompt_lower:
        return Intent(
            category=IntentCategory.TASK_REQUEST,
            confidence=rules.confidence.default_task,
            requires_memory=False,
            requires_archive=False,
            metadata={"match": "empty_prompt"},
        )

    best_category: IntentCategory | None = None
    best_keyword_hits = 0
    best_regex_hits = 0
    matched_categories: list[IntentCategory] = []

    for category in rules.priority_categories():
        cat_rules = rules.category_rules(category)
        keyword_hits, regex_hits = _score_category(prompt, prompt_lower, cat_rules)
        if keyword_hits == 0 and regex_hits == 0:
            continue

        matched_categories.append(category)
        total_hits = keyword_hits + regex_hits
        best_total = best_keyword_hits + best_regex_hits
        if best_category is None or total_hits > best_total:
            best_category = category
            best_keyword_hits = keyword_hits
            best_regex_hits = regex_hits
        elif total_hits == best_total and best_category is not None:
            # Tie-break using configured priority order (first wins).
            current_idx = rules.priority.index(category.value)
            best_idx = rules.priority.index(best_category.value)
            if current_idx < best_idx:
                best_category = category
                best_keyword_hits = keyword_hits
                best_regex_hits = regex_hits

    if best_category is None:
        return Intent(
            category=IntentCategory.TASK_REQUEST,
            confidence=rules.confidence.default_task,
            requires_memory=False,
            requires_archive=False,
            metadata={"match": "default"},
        )

    cat_rules = rules.category_rules(best_category)
    if best_regex_hits > 0 and best_keyword_hits > 0:
        confidence = rules.confidence.multiple_matches
    elif best_regex_hits > 0:
        confidence = rules.confidence.regex_match
    else:
        confidence = rules.confidence.keyword_match

    if len(matched_categories) > 1:
        confidence = min(confidence, rules.confidence.keyword_match)

    return Intent(
        category=best_category,
        confidence=confidence,
        requires_memory=cat_rules.requires_memory,
        requires_archive=cat_rules.requires_archive,
        metadata={
            "match": "rules",
            "keyword_hits": best_keyword_hits,
            "regex_hits": best_regex_hits,
            "matched_categories": [c.value for c in matched_categories],
        },
    )


class RuleBasedIntentRouter:
    """Classifies prompts using YAML rules with optional LLM fallback."""

    def __init__(
        self,
        rules: RoutingRules | None = None,
        llm: Any = None,
        llm_classify: LLMClassifyFn | None = None,
    ) -> None:
        self.rules = rules or load_routing_rules()
        self._llm = llm
        self._llm_classify = llm_classify

    async def classify(self, prompt: str) -> Intent:
        """Classify prompt; uses LLM when rule confidence is below threshold."""
        intent = classify_with_rules(prompt, self.rules)

        if intent.confidence >= self.rules.ambiguous_threshold:
            return intent

        llm_intent = await self._try_llm_fallback(prompt)
        if llm_intent is not None:
            return llm_intent

        return intent

    async def _try_llm_fallback(self, prompt: str) -> Intent | None:
        if self._llm_classify is not None:
            try:
                return await self._llm_classify(prompt)
            except Exception:
                logger.exception("LLM classify callback failed")
                return None

        if self._llm is None:
            return None

        classify_fn = getattr(self._llm, "classify_intent", None)
        if callable(classify_fn):
            try:
                result = classify_fn(prompt)
                if hasattr(result, "__await__"):
                    return await result
                return result  # type: ignore[return-value]
            except Exception:
                logger.exception("LLM classify_intent failed")
                return None

        return None

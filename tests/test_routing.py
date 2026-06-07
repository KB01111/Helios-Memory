"""Unit tests for rule-based intent routing."""

from __future__ import annotations

from pathlib import Path

import pytest

from helios_memory.models import IntentCategory
from helios_memory.routing.intent_router import RuleBasedIntentRouter, classify_with_rules
from helios_memory.routing.rules import RoutingRules, load_routing_rules


@pytest.fixture
def rules(routing_rules: RoutingRules) -> RoutingRules:
    return routing_rules


class TestClassifyWithRulesCategories:
    """Each intent category is classified correctly by rules alone."""

    @pytest.mark.parametrize(
        ("prompt", "expected"),
        [
            ("Hello there, how are you today?", IntentCategory.SMALL_TALK),
            ("Thanks for your help!", IntentCategory.SMALL_TALK),
            ("Please implement a login endpoint for me.", IntentCategory.TASK_REQUEST),
            ("Can you fix the bug in the parser?", IntentCategory.TASK_REQUEST),
            ("Do you remember what we decided last time?", IntentCategory.MEMORY_LOOKUP_NEEDED),
            ("What did I say about my preference for dark mode?", IntentCategory.MEMORY_LOOKUP_NEEDED),
            ("Where is the README in the repository?", IntentCategory.PROJECT_CONTEXT_NEEDED),
            ("Which file contains the authentication module?", IntentCategory.PROJECT_CONTEXT_NEEDED),
            ("My API key is sk-live-abc123", IntentCategory.SENSITIVE_REQUEST),
            ("Store this password in the config", IntentCategory.SENSITIVE_REQUEST),
        ],
    )
    def test_category_classification(
        self,
        rules: RoutingRules,
        prompt: str,
        expected: IntentCategory,
    ) -> None:
        intent = classify_with_rules(prompt, rules)
        assert intent.category == expected


class TestClassifyWithRulesPriority:
    """Higher-priority categories win when multiple patterns match."""

    def test_sensitive_beats_memory_lookup_on_tie_break(self, rules: RoutingRules) -> None:
        """When hit counts tie, configured priority favors sensitive_request."""
        prompt = "Remember my password and secret from before"
        intent = classify_with_rules(prompt, rules)
        assert intent.category == IntentCategory.SENSITIVE_REQUEST

    def test_sensitive_beats_task_when_more_sensitive_hits(self, rules: RoutingRules) -> None:
        prompt = "Please help me rotate my password and api key token"
        intent = classify_with_rules(prompt, rules)
        assert intent.category == IntentCategory.SENSITIVE_REQUEST

    def test_memory_lookup_beats_project_context(self, rules: RoutingRules) -> None:
        prompt = "What did we decide about the repository structure?"
        intent = classify_with_rules(prompt, rules)
        assert intent.category == IntentCategory.MEMORY_LOOKUP_NEEDED
        assert intent.requires_memory is True

    def test_priority_order_matches_config(self, rules: RoutingRules) -> None:
        assert rules.priority[0] == "sensitive_request"
        assert rules.priority[-1] == "task_request"


class TestClassifyWithRulesEdgeCases:
    """Ambiguous prompts, defaults, and mixed signals."""

    def test_empty_prompt_defaults_to_task(self, rules: RoutingRules) -> None:
        intent = classify_with_rules("   ", rules)
        assert intent.category == IntentCategory.TASK_REQUEST
        assert intent.metadata.get("match") == "empty_prompt"

    def test_unmatched_prompt_defaults_to_task(self, rules: RoutingRules) -> None:
        intent = classify_with_rules("xyzzy plugh", rules)
        assert intent.category == IntentCategory.TASK_REQUEST
        assert intent.metadata.get("match") == "default"

    def test_mixed_signals_records_multiple_matches(self, rules: RoutingRules) -> None:
        prompt = "Hi, please remember to update the readme in the repo"
        intent = classify_with_rules(prompt, rules)
        matched = intent.metadata.get("matched_categories", [])
        assert len(matched) >= 2

    def test_confidence_lowered_when_multiple_categories_match(
        self,
        rules: RoutingRules,
    ) -> None:
        prompt = "Hello, can you help me find the readme file?"
        intent = classify_with_rules(prompt, rules)
        matched = intent.metadata.get("matched_categories", [])
        if len(matched) > 1:
            assert intent.confidence <= rules.confidence.keyword_match


class TestSensitiveDetection:
    """Sensitive request patterns are detected before cloud routing."""

    @pytest.mark.parametrize(
        "prompt",
        [
            "Here is my ssn: 123-45-6789",
            "Load credentials.json for deployment",
            "The secret token is in .env",
            "My credit card number is 4111",
            "ssh key path is ~/.ssh/id_rsa",
        ],
    )
    def test_sensitive_patterns(self, rules: RoutingRules, prompt: str) -> None:
        intent = classify_with_rules(prompt, rules)
        assert intent.category == IntentCategory.SENSITIVE_REQUEST


class TestRuleBasedIntentRouterLLMFallback:
    """Optional LLM fallback when rule confidence is below threshold."""

    @pytest.mark.asyncio
    async def test_llm_fallback_when_ambiguous(self, rules: RoutingRules) -> None:
        rules.ambiguous_threshold = 0.99

        async def llm_classify(prompt: str):
            from helios_memory.models import Intent

            return Intent(
                category=IntentCategory.MEMORY_LOOKUP_NEEDED,
                confidence=0.95,
                requires_memory=True,
                metadata={"match": "llm"},
            )

        router = RuleBasedIntentRouter(rules=rules, llm_classify=llm_classify)
        intent = await router.classify("something vague")
        assert intent.category == IntentCategory.MEMORY_LOOKUP_NEEDED
        assert intent.metadata.get("match") == "llm"

    @pytest.mark.asyncio
    async def test_no_llm_when_confident(self, rules: RoutingRules) -> None:
        called = False

        async def llm_classify(prompt: str):
            nonlocal called
            called = True
            return None

        router = RuleBasedIntentRouter(rules=rules, llm_classify=llm_classify)
        intent = await router.classify("Hello!")
        assert intent.category == IntentCategory.SMALL_TALK
        assert called is False


def test_load_routing_rules_from_project_config() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config" / "routing_rules.yaml"
    rules = load_routing_rules(config_path)
    assert "sensitive_request" in rules.categories
    assert rules.ambiguous_threshold == 0.5

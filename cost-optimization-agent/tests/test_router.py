"""Unit tests for router.py's decision logic — no live API calls.

Availability is injected as a plain dict so these tests exercise only
the routing/selection logic, never network code or provider SDKs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from router import NoEligibleModelError, Router, classify_complexity, estimate_tokens

ALL_AVAILABLE = {"ollama": True, "openai": True, "anthropic": True, "gemini": True}
NO_OLLAMA = {"ollama": False, "openai": True, "anthropic": True, "gemini": True}
NONE_AVAILABLE = {"ollama": False, "openai": False, "anthropic": False, "gemini": False}


def test_classify_complexity_simple():
    assert classify_complexity("What is the capital of France?") == "simple"
    assert classify_complexity("Format this as JSON") == "simple"


def test_classify_complexity_complex_by_keyword():
    assert classify_complexity("Design the architecture for a new microservice") == "complex"


def test_classify_complexity_complex_by_length():
    long_task = "Please " + "look into this issue carefully " * 10 + "and give me a summary."
    assert classify_complexity(long_task) == "complex"


def test_simple_task_prefers_ollama_when_available():
    router = Router(availability=ALL_AVAILABLE)
    decision = router.select("What's 2+2?")
    assert decision.chosen.provider == "ollama"
    assert decision.estimated_cost_usd == 0.0


def test_simple_task_falls_back_to_cheapest_when_ollama_unavailable():
    router = Router(availability=NO_OLLAMA)
    decision = router.select("What's 2+2?")
    assert decision.chosen.provider != "ollama"


def test_complex_task_excludes_simple_tier_models():
    router = Router(availability=ALL_AVAILABLE)
    decision = router.select("Design the architecture for a distributed rate limiter")
    assert decision.complexity == "complex"
    assert decision.chosen.tier in ("complex", "premium")


def test_cost_ceiling_excludes_expensive_models():
    router = Router(availability=NO_OLLAMA)
    decision = router.select(
        "Design the architecture for a distributed rate limiter",
        cost_ceiling_usd=0.001,
    )
    assert decision.within_ceiling is True
    assert decision.estimated_cost_usd <= 0.001


def test_no_eligible_model_raises_when_nothing_available():
    router = Router(availability=NONE_AVAILABLE)
    with pytest.raises(NoEligibleModelError):
        router.select("Design a system")


def test_fallback_chain_is_sorted_by_cost_ascending():
    router = Router(availability=NO_OLLAMA)
    task = "What's 2+2?"
    decision = router.select(task)
    input_tokens = estimate_tokens(task)
    costs = [m.estimated_cost(input_tokens, 256) for m in decision.fallback_chain]
    assert costs == sorted(costs)


def test_most_expensive_returns_a_catalog_model():
    router = Router(availability=ALL_AVAILABLE)
    priciest = router.most_expensive()
    assert priciest in router.models
    assert all(
        priciest.estimated_cost(1000, 1000) >= m.estimated_cost(1000, 1000)
        for m in router.models
    )

"""Cost- and quality-aware model selection logic.

The Router loads the model catalog from config/models.yaml and, given a
task string, decides which (provider, model) pair to use plus an ordered
fallback chain. It has no knowledge of how to actually call a provider —
that's agent.py's job — so it can be unit tested without any network
access or API keys (see tests/test_router.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "models.yaml"

# Lightweight heuristic keywords that push a task into the "complex" tier.
COMPLEX_KEYWORDS = (
    "analyze", "architecture", "design", "debug", "refactor", "explain in depth",
    "compare", "strategy", "root cause", "optimi", "plan", "why does", "troubleshoot",
)


@dataclass(frozen=True)
class ModelOption:
    """A single (provider, model) offering from the catalog, with pricing."""

    provider: str
    model: str
    tier: str
    cost_per_1m_input: float
    cost_per_1m_output: float
    avg_latency_ms: int

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Return the estimated USD cost for the given token counts."""
        return (
            input_tokens / 1_000_000 * self.cost_per_1m_input
            + output_tokens / 1_000_000 * self.cost_per_1m_output
        )


@dataclass
class RoutingDecision:
    """The router's chosen model plus context explaining and backing it up."""

    complexity: str
    chosen: ModelOption
    fallback_chain: list[ModelOption]
    estimated_cost_usd: float
    within_ceiling: bool
    reason: str


class NoEligibleModelError(Exception):
    """Raised when no configured model is available for the task's tier."""


def classify_complexity(task: str) -> str:
    """Heuristically classify a task as 'simple' or 'complex'.

    Simple: short, single-step lookups/classification/formatting requests.
    Complex: multi-step reasoning, analysis, design, or debugging requests.
    This is a lightweight heuristic (word count + keyword match) rather
    than a model call, so classification itself costs nothing.
    """
    text = task.lower()
    if any(kw in text for kw in COMPLEX_KEYWORDS):
        return "complex"
    if len(text.split()) > 40:
        return "complex"
    return "simple"


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), used for dry-run cost previews."""
    return max(1, len(text) // 4)


class Router:
    """Selects the cheapest eligible model for a task from the catalog."""

    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        availability: dict[str, bool] | Callable[[str], bool] | None = None,
    ) -> None:
        """Load the catalog.

        `availability` lets callers control which providers are considered
        reachable: a dict of provider name -> bool, a callable, or None
        (meaning "treat every provider as available"). Tests pass a dict
        so routing decisions can be verified with zero network access.
        """
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.models: list[ModelOption] = [
            ModelOption(
                provider=provider_name,
                model=m["name"],
                tier=m["tier"],
                cost_per_1m_input=m["cost_per_1m_input"],
                cost_per_1m_output=m["cost_per_1m_output"],
                avg_latency_ms=m.get("avg_latency_ms", 0),
            )
            for provider_name, provider_cfg in config["providers"].items()
            for m in provider_cfg["models"]
        ]
        self.routing_cfg = config["routing"]
        self._availability = availability

    def most_expensive(self) -> ModelOption:
        """Return the catalog's priciest model, used as the 'always use the
        most expensive model' baseline for savings reporting."""
        return max(self.models, key=lambda m: m.estimated_cost(1000, 1000))

    def _is_available(self, provider: str) -> bool:
        if self._availability is None:
            return True
        if callable(self._availability):
            return bool(self._availability(provider))
        return bool(self._availability.get(provider, False))

    def select(
        self,
        task: str,
        cost_ceiling_usd: float | None = None,
        estimated_output_tokens: int = 256,
    ) -> RoutingDecision:
        """Pick the cheapest available, tier-eligible model for `task`.

        Returns a RoutingDecision containing the chosen model and an
        ordered fallback chain (cheapest-first, chosen model included as
        element 0) that agent.py can walk through on provider errors.
        """
        complexity = classify_complexity(task)
        ceiling = (
            cost_ceiling_usd
            if cost_ceiling_usd is not None
            else self.routing_cfg["default_cost_ceiling_usd"]
        )
        eligible_tiers = set(self.routing_cfg["tier_eligibility"][complexity])
        input_tokens = estimate_tokens(task)

        candidates = [
            m for m in self.models
            if m.tier in eligible_tiers and self._is_available(m.provider)
        ]
        if not candidates:
            raise NoEligibleModelError(
                f"no available provider offers a '{complexity}'-eligible model"
            )

        priced = [
            (m, m.estimated_cost(input_tokens, estimated_output_tokens))
            for m in candidates
        ]
        within_ceiling = [p for p in priced if p[1] <= ceiling]
        used_ceiling = bool(within_ceiling)
        pool = within_ceiling if used_ceiling else priced

        prefer_local = bool(self.routing_cfg.get("prefer_local_for_simple")) and complexity == "simple"

        def sort_key(pair: tuple[ModelOption, float]) -> tuple[int, float]:
            model, cost = pair
            is_local = prefer_local and model.provider == "ollama"
            return (0 if is_local else 1, cost)

        pool.sort(key=sort_key)
        fallback_chain = [m for m, _ in pool]
        chosen, chosen_cost = pool[0]

        reason_bits = [
            f"complexity={complexity}",
            f"eligible tiers={sorted(eligible_tiers)}",
        ]
        reason_bits.append(
            f"within cost ceiling ${ceiling:.4f}" if used_ceiling
            else f"no candidate under ceiling ${ceiling:.4f}; picked cheapest available"
        )
        if chosen.provider == "ollama":
            reason_bits.append("local model preferred (free, available)")

        return RoutingDecision(
            complexity=complexity,
            chosen=chosen,
            fallback_chain=fallback_chain,
            estimated_cost_usd=chosen_cost,
            within_ceiling=used_ceiling,
            reason="; ".join(reason_bits),
        )

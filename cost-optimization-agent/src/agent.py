"""Orchestration: task -> route -> call provider (with fallback) -> log cost."""

from __future__ import annotations

import time
from dataclasses import dataclass

from cost_tracker import CostTracker
from providers.anthropic_provider import AnthropicProvider
from providers.base import Provider, ProviderError
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from providers.openai_provider import OpenAIProvider
from router import NoEligibleModelError, Router


def build_default_providers() -> dict[str, Provider]:
    """Instantiate one adapter per supported provider.

    Adding a fifth provider means adding one line here (and one adapter
    file + one config/models.yaml entry) — nothing else changes.
    """
    return {
        "ollama": OllamaProvider(),
        "openai": OpenAIProvider(),
        "anthropic": AnthropicProvider(),
        "gemini": GeminiProvider(),
    }


@dataclass
class RunResult:
    """Outcome of ScalatenAgent.run(), covering both dry-run and live calls."""

    dry_run: bool
    complexity: str
    provider: str
    model: str
    estimated_cost_usd: float
    reason: str
    text: str | None = None
    actual_cost_usd: float | None = None
    latency_ms: float | None = None
    attempts: list[str] | None = None


class ScalatenAgent:
    """Ties the router, provider adapters, and cost tracker together."""

    def __init__(
        self,
        router: Router | None = None,
        providers: dict[str, Provider] | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.providers = providers or build_default_providers()
        self.router = router or Router(
            availability={name: p.is_available() for name, p in self.providers.items()}
        )
        self.cost_tracker = cost_tracker or CostTracker()

    def run(
        self,
        task: str,
        cost_ceiling_usd: float | None = None,
        dry_run: bool = False,
        estimated_output_tokens: int = 256,
    ) -> RunResult:
        """Route `task` to the best available model and, unless `dry_run`,
        execute it — walking the fallback chain if a provider errors or
        rate-limits, so a single provider outage never crashes the agent.
        """
        try:
            decision = self.router.select(
                task,
                cost_ceiling_usd=cost_ceiling_usd,
                estimated_output_tokens=estimated_output_tokens,
            )
        except NoEligibleModelError as exc:
            return RunResult(
                dry_run=dry_run,
                complexity="unknown",
                provider="none",
                model="none",
                estimated_cost_usd=0.0,
                reason=str(exc),
            )

        if dry_run:
            return RunResult(
                dry_run=True,
                complexity=decision.complexity,
                provider=decision.chosen.provider,
                model=decision.chosen.model,
                estimated_cost_usd=decision.estimated_cost_usd,
                reason=decision.reason,
            )

        attempts: list[str] = []
        for option in decision.fallback_chain:
            provider_impl = self.providers.get(option.provider)
            if provider_impl is None:
                attempts.append(f"{option.provider}/{option.model}: no adapter registered")
                continue

            start = time.monotonic()
            try:
                response = provider_impl.generate(task, option.model)
            except ProviderError as exc:
                attempts.append(f"{option.provider}/{option.model}: {exc}")
                continue
            latency_ms = (time.monotonic() - start) * 1000

            cost_usd = option.estimated_cost(response.input_tokens, response.output_tokens)
            self.cost_tracker.log_call(
                provider=option.provider,
                model=option.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                task_preview=task,
            )
            return RunResult(
                dry_run=False,
                complexity=decision.complexity,
                provider=option.provider,
                model=option.model,
                estimated_cost_usd=decision.estimated_cost_usd,
                reason=decision.reason,
                text=response.text,
                actual_cost_usd=cost_usd,
                latency_ms=latency_ms,
                attempts=attempts,
            )

        return RunResult(
            dry_run=False,
            complexity=decision.complexity,
            provider="none",
            model="none",
            estimated_cost_usd=decision.estimated_cost_usd,
            reason="every candidate in the fallback chain failed",
            attempts=attempts,
        )

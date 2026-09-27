"""Abstract interface every LLM provider adapter must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderResponse:
    """Result of a single generation call, with token usage for cost accounting."""

    text: str
    input_tokens: int
    output_tokens: int


class ProviderError(Exception):
    """Raised when a provider call fails (auth, rate limit, network, etc.)."""


class Provider(ABC):
    """Common interface for all LLM provider adapters.

    Adding a new provider means creating one new file implementing this
    class and registering it in ``router.PROVIDER_REGISTRY`` — nothing
    else in the codebase needs to change.
    """

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is configured and reachable."""

    @abstractmethod
    def generate(self, prompt: str, model: str, **kwargs) -> ProviderResponse:
        """Run a completion and return text plus actual token usage.

        Must raise ProviderError (not a provider-SDK-specific exception)
        on failure so the agent's fallback chain can catch one type.
        """

"""Anthropic provider adapter."""

from __future__ import annotations

import os

from .base import Provider, ProviderError, ProviderResponse


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self) -> None:
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, model: str, **kwargs) -> ProviderResponse:
        if not self.api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")

        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError("anthropic package is not installed") from exc

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            resp = client.messages.create(
                model=model,
                max_tokens=kwargs.get("max_tokens", 1024),
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 - normalize any SDK error
            raise ProviderError(f"anthropic request failed: {exc}") from exc

        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        return ProviderResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )

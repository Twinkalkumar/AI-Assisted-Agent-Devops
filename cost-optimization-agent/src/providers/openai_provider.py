"""OpenAI provider adapter."""

from __future__ import annotations

import os

from .base import Provider, ProviderError, ProviderResponse


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, model: str, **kwargs) -> ProviderResponse:
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY is not set")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError("openai package is not installed") from exc

        try:
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 - normalize any SDK error
            raise ProviderError(f"openai request failed: {exc}") from exc

        usage = resp.usage
        return ProviderResponse(
            text=resp.choices[0].message.content or "",
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

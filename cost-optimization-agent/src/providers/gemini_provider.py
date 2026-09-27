"""Google Gemini provider adapter."""

from __future__ import annotations

import os

from .base import Provider, ProviderError, ProviderResponse


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, model: str, **kwargs) -> ProviderResponse:
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is not set")

        try:
            from google import genai
        except ImportError as exc:
            raise ProviderError("google-genai package is not installed") from exc

        try:
            client = genai.Client(api_key=self.api_key)
            resp = client.models.generate_content(model=model, contents=prompt)
        except Exception as exc:  # noqa: BLE001 - normalize any SDK error
            raise ProviderError(f"gemini request failed: {exc}") from exc

        usage = getattr(resp, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        return ProviderResponse(
            text=resp.text or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

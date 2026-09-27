"""Ollama provider adapter — local/self-hosted models, treated as $0 cost."""

from __future__ import annotations

import os

import requests

from .base import Provider, ProviderError, ProviderResponse


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self) -> None:
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def generate(self, prompt: str, model: str, **kwargs) -> ProviderResponse:
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=kwargs.get("timeout", 120),
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"ollama request failed: {exc}") from exc

        data = resp.json()
        return ProviderResponse(
            text=data.get("response", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

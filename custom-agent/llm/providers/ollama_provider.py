import requests

from ..base import LLMProvider


class OllamaProvider(LLMProvider):
    """Talks to a local Ollama server - no API key required."""

    def __init__(self, model: str, temperature: float, max_tokens: int, base_url: str):
        super().__init__(model, temperature, max_tokens)
        self._url = base_url.rstrip("/") + "/api/chat"

    def chat(self, messages: list[dict]) -> str:
        response = requests.post(
            self._url,
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            },
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

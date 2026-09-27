from ..base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str, temperature: float, max_tokens: int, api_key: str):
        super().__init__(model, temperature, max_tokens)
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)

    def chat(self, messages: list[dict]) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content or ""

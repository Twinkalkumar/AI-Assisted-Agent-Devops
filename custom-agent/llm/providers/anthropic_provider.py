from ..base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, temperature: float, max_tokens: int, api_key: str):
        super().__init__(model, temperature, max_tokens)
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)

    def chat(self, messages: list[dict]) -> str:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]

        response = self._client.messages.create(
            model=self.model,
            system=system,
            messages=turns,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return "".join(block.text for block in response.content if block.type == "text")

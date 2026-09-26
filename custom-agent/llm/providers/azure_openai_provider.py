from ..base import LLMProvider


class AzureOpenAIProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        temperature: float,
        max_tokens: int,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str,
    ):
        super().__init__(model, temperature, max_tokens)
        from openai import AzureOpenAI

        self._deployment = deployment
        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    def chat(self, messages: list[dict]) -> str:
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content or ""

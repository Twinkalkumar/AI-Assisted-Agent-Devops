from ..base import LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini via the google-genai SDK (pip install google-genai)."""

    def __init__(self, model: str, temperature: float, max_tokens: int, api_key: str):
        super().__init__(model, temperature, max_tokens)
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=api_key)

    def chat(self, messages: list[dict]) -> str:
        system_text = "\n".join(m["content"] for m in messages if m["role"] == "system")

        # Gemini has no "system" turn in contents, and calls the assistant role "model".
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
            if m["role"] != "system"
        ]

        response = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._types.GenerateContentConfig(
                system_instruction=system_text,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )
        return response.text or ""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Common interface every LLM backend must implement.

    The agent core only ever talks to this interface, so switching
    providers never touches agent/tool code - only config.yaml + .env.
    """

    def __init__(self, model: str, temperature: float = 0.2, max_tokens: int = 4096):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def chat(self, messages: list[dict]) -> str:
        """messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]

        Returns the assistant's raw text reply.
        """
        raise NotImplementedError

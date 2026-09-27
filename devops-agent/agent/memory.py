class ConversationMemory:
    """Plain list of chat messages shared with the LLM each turn."""

    def __init__(self, system_prompt: str):
        self._messages = [{"role": "system", "content": system_prompt}]

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self._messages.append({"role": "assistant", "content": content})

    @property
    def messages(self) -> list[dict]:
        return list(self._messages)

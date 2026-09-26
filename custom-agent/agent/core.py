import json
import re

from llm.base import LLMProvider
from tools.base import Tool

from .memory import ConversationMemory
from .prompts import build_system_prompt

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_response(raw: str) -> dict:
    """LLMs sometimes wrap JSON in ```...``` fences or add stray text around it.
    Try a straight parse first, then fall back to extracting the outermost {...}.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(raw)
        if not match:
            raise ValueError(f"Model response was not JSON:\n{raw}")
        return json.loads(match.group(0))


class Agent:
    """Provider-agnostic ReAct-style loop: think -> call a tool -> observe -> repeat."""

    def __init__(self, llm: LLMProvider, tools: list[Tool], max_iterations: int = 12):
        self._llm = llm
        self._tools_by_name = {t.name: t for t in tools}
        self._max_iterations = max_iterations
        self._system_prompt = build_system_prompt(tools)

    def run(self, task: str) -> str:
        memory = ConversationMemory(self._system_prompt)
        memory.add_user(task)

        for step in range(1, self._max_iterations + 1):
            raw_reply = self._llm.chat(memory.messages)
            memory.add_assistant(raw_reply)

            try:
                decision = _parse_json_response(raw_reply)
            except ValueError as exc:
                memory.add_user(f"Error: {exc}. Respond with valid JSON only.")
                continue

            if "final_answer" in decision:
                return decision["final_answer"]

            tool_name = decision.get("tool")
            tool = self._tools_by_name.get(tool_name)
            if tool is None:
                memory.add_user(
                    f"Error: unknown tool '{tool_name}'. "
                    f"Available tools: {list(self._tools_by_name)}"
                )
                continue

            args = decision.get("args", {})
            try:
                observation = tool.run(**args)
            except Exception as exc:  # tool failures are fed back to the LLM, not fatal
                observation = f"Error running {tool_name}: {exc}"

            print(f"[step {step}] tool={tool_name} args={args}")
            memory.add_user(f"Tool result:\n{observation}")

        return (
            f"Stopped after {self._max_iterations} steps without a final answer. "
            "Check the output directory for partial progress."
        )

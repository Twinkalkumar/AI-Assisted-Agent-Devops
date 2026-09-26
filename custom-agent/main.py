import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from agent import Agent
from llm import build_llm
from tools import get_enabled_tools

BASE_DIR = Path(__file__).parent


def load_config() -> dict:
    with open(BASE_DIR / "config" / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    if len(sys.argv) >= 2:
        task = " ".join(sys.argv[1:])
    else:
        task = input("Enter task: ").strip()
        if not task:
            print('No task given. Usage: python main.py "<task description>"')
            sys.exit(1)

    load_dotenv(BASE_DIR / ".env")
    config = load_config()

    output_dir = (BASE_DIR / config["agent"]["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    llm = build_llm(config["llm"])
    tools = get_enabled_tools(config["tools"]["enabled"], output_dir)
    agent = Agent(llm, tools, max_iterations=config["agent"]["max_iterations"])

    print(f"Running task with provider={config['llm']['provider']} model={config['llm']['model']}")
    result = agent.run(task)

    print("\n=== Final answer ===")
    print(result)
    print(f"\nOutputs written under: {output_dir}")


if __name__ == "__main__":
    main()

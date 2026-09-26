# Custom Agent

A minimal, provider-agnostic agent skeleton (Python) that can be asked to do
almost any DevOps/automation task in plain English - e.g. design a Kubernetes
architecture and generate manifests, write a GitHub Actions deployment
workflow, or generate a shell/PowerShell script - and it writes the results
to `output/`.

## Design

- `llm/` - one abstract interface (`LLMProvider.chat`) with a provider per
  backend (OpenAI, Anthropic, Azure OpenAI, Ollama). **All LLM selection lives
  in `config/config.yaml` (`llm.provider` / `llm.model`) + `.env` (API keys)** -
  nothing else in the codebase needs to change to switch models/providers.
- `tools/` - pluggable actions the agent can call: `write_file`, `read_file`,
  `list_directory`, and an opt-in `run_command`. Add a new tool by subclassing
  `tools.base.Tool` and registering it in `tools/registry.py`.
- `agent/` - a small ReAct-style loop: the LLM replies with one JSON object per
  turn, either `{"tool": ..., "args": {...}}` or `{"final_answer": ...}`; the
  loop executes the tool and feeds the result back until it's done.

## Setup

```bash
cd custom-agent
pip install -r requirements.txt
cp .env.example .env   # fill in the API key for whichever provider you pick
```

Edit `config/config.yaml` to choose the provider/model:

```yaml
llm:
  provider: openai   # openai | anthropic | azure_openai | ollama
  model: gpt-4o-mini
```

## Run

```bash
python main.py "Create a Kubernetes architecture to deploy a Node.js API with Postgres"
```

Generated files land in `custom-agent/output/`. See `examples/example_tasks.md`
for more sample prompts (Kubernetes, GitHub workflows, shell/PowerShell scripts).

## Adding a new tool

1. Create a class in `tools/` subclassing `Tool` with `name`, `description`,
   `parameters` (JSON schema) and a `run(**kwargs)` method.
2. Register it in `_TOOL_BUILDERS` in `tools/registry.py`.
3. Add its name to `tools.enabled` in `config/config.yaml`.

## Adding a new LLM provider

1. Create a class in `llm/providers/` subclassing `LLMProvider` with a
   `chat(messages)` method.
2. Add a branch for it in `llm/factory.py::build_llm`.
3. Set `llm.provider` in `config/config.yaml` and add its env vars to `.env`.

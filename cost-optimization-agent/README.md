# Scalaten — Multi-Provider LLM Cost-Optimization Agent

Scalaten receives a task, picks the cheapest provider/model that can meet
the task's quality requirements, routes the request, tracks spend, and
reports savings versus always using the most expensive model.

## Architecture

```
task ─▶ router.py ─▶ (provider, model) + fallback chain ─▶ agent.py
                                                              │
                                     calls providers/*.py ◀───┘
                                              │
                                     cost_tracker.py logs to logs/usage.jsonl
```

- **`src/router.py`** — pure decision logic: classifies task complexity
  (simple vs. complex, via keyword/length heuristics), filters the model
  catalog by tier eligibility and cost ceiling, and returns the cheapest
  eligible model plus an ordered fallback chain. No network calls, no
  provider SDKs — fully unit-testable (see `tests/test_router.py`).
- **`src/providers/*.py`** — one adapter per provider, all implementing
  the `Provider` interface in `providers/base.py` (`is_available()`,
  `generate()`). Adding a 5th provider = one new adapter file + one
  registry line in `agent.py::build_default_providers` + one catalog
  entry in `config/models.yaml`. Nothing else changes.
- **`src/agent.py`** — orchestration: routes the task, then walks the
  fallback chain calling each provider in turn until one succeeds
  (provider outages/rate limits fall through to the next-cheapest
  option instead of crashing the agent).
- **`src/cost_tracker.py`** — appends one JSON line per call to
  `logs/usage.jsonl` (provider, model, tokens, cost, latency) and
  aggregates totals / per-provider breakdown / savings vs. baseline.
- **`config/models.yaml`** — the only place pricing and model lists
  live; update rates here without touching code.

## Setup

```bash
cd cost-optimization-agent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and fill in the API keys for whichever providers you use
```

You don't need every provider configured — the router only considers
providers that report themselves available (API key present, or for
Ollama, the base URL responds).

## Usage

Preview the routing decision without spending anything:

```bash
python src/main.py run "What's the capital of France?" --dry-run
```

Route and actually execute a task:

```bash
python src/main.py run "Design the architecture for a rate limiter" --cost-ceiling 0.02
```

See total spend, per-provider breakdown, and savings vs. always using the
most expensive configured model:

```bash
python src/main.py report
```

## How routing decisions are made

1. **Classify complexity** — a lightweight heuristic (keyword match +
   word count) labels the task `simple` or `complex`. No model call is
   used for this step, so classification itself is free.
2. **Filter by tier eligibility** — `simple` tasks may use any tier;
   `complex` tasks are restricted to `complex`/`premium` tier models
   (configurable in `config/models.yaml` under `routing.tier_eligibility`).
3. **Filter by availability** — only providers with a configured key (or,
   for Ollama, a reachable base URL) are considered.
4. **Filter by cost ceiling** — candidates are estimated using a rough
   token count (~4 chars/token) and dropped if projected cost exceeds
   `--cost-ceiling` (default: `routing.default_cost_ceiling_usd`). If
   *nothing* fits under the ceiling, the cheapest available candidate is
   used anyway rather than failing the request outright.
5. **Prefer local** — for `simple` tasks, an available Ollama model is
   always chosen first (it's free).
6. **Build a fallback chain** — the remaining eligible candidates are
   sorted cheapest-first. If the top choice's provider call fails, the
   agent tries the next one automatically.

## Testing

```bash
pytest tests/
```

Router tests inject availability as a plain dict, so they validate the
decision logic with zero network access and no API keys required.

## Notes

- `.env` is git-ignored — never commit real API keys.
- Actual cost logging uses the token counts returned by each provider's
  API response (not the pre-call estimate), so `report` reflects real
  spend.

"""Per-call cost/token/latency logging and spend reporting.

Every provider call is appended as one JSON line to logs/usage.jsonl so
the log survives process restarts and can be inspected/replayed with
any standard JSONL tooling.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from router import ModelOption

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "usage.jsonl"


@dataclass
class UsageRecord:
    """A single logged provider call."""

    timestamp: float
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    task_preview: str


class CostTracker:
    """Appends usage records to a JSONL log and aggregates them into reports."""

    def __init__(self, log_path: str | Path = DEFAULT_LOG_PATH) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_call(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: float,
        task_preview: str = "",
    ) -> UsageRecord:
        """Record one provider call and append it to the usage log."""
        record = UsageRecord(
            timestamp=time.time(),
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            task_preview=task_preview[:120],
        )
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")
        return record

    def _read_all(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        records = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def summary(self, baseline_model: ModelOption | None = None) -> dict:
        """Return running totals, a per-provider breakdown, and (if a
        baseline model is given) estimated savings versus always using it.
        """
        records = self._read_all()
        total_cost = sum(r["cost_usd"] for r in records)

        by_provider: dict[str, dict] = {}
        for r in records:
            bucket = by_provider.setdefault(
                r["provider"],
                {"calls": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0},
            )
            bucket["calls"] += 1
            bucket["cost_usd"] += r["cost_usd"]
            bucket["input_tokens"] += r["input_tokens"]
            bucket["output_tokens"] += r["output_tokens"]

        result: dict = {
            "total_calls": len(records),
            "total_cost_usd": total_cost,
            "by_provider": by_provider,
        }

        if baseline_model is not None and records:
            baseline_cost = sum(
                baseline_model.estimated_cost(r["input_tokens"], r["output_tokens"])
                for r in records
            )
            result["baseline_model"] = f"{baseline_model.provider}/{baseline_model.model}"
            result["baseline_cost_usd"] = baseline_cost
            result["savings_usd"] = baseline_cost - total_cost
            result["savings_pct"] = (
                (baseline_cost - total_cost) / baseline_cost * 100
                if baseline_cost > 0
                else 0.0
            )

        return result

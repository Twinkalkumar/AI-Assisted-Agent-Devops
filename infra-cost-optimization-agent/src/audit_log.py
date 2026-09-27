"""Append-only audit trail (logs/audit.jsonl) plus structured JSON
application logging (logs/agent.jsonl).

Both are JSONL: one JSON object per line, opened in append mode, never
rewritten — this is what makes the audit log a durable record of what
CostGuard actually did.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AUDIT_LOG_PATH = LOGS_DIR / "audit.jsonl"
APP_LOG_PATH = LOGS_DIR / "agent.jsonl"


class JsonLogFormatter(logging.Formatter):
    """Formats each log record as one JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a JSONL file handler (logs/agent.jsonl) to the root logger,
    in addition to whatever handlers already exist (e.g. console output).
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(APP_LOG_PATH, encoding="utf-8")
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


def record_audit_event(
    event_type: str,
    finding_id: str,
    provider: str,
    account: str,
    resource_id: str,
    action_type: str,
    approved_by: str,
    rollback_command: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append one entry to the audit log. Never overwrites or removes
    previous entries — this is the record of what happened, and by whom
    it was approved, for every executed or rolled-back action.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,  # "executed" | "rolled_back" | "execution_failed"
        "finding_id": finding_id,
        "provider": provider,
        "account": account,
        "resource_id": resource_id,
        "action_type": action_type,
        "approved_by": approved_by,  # e.g. "auto (LOW risk)", "cli:alice", "webhook:slack"
        "rollback_command": rollback_command,
        "details": details or {},
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_audit_log() -> list[dict[str, Any]]:
    """Read every entry ever written to the audit log, in order."""
    if not AUDIT_LOG_PATH.exists():
        return []
    entries = []
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries

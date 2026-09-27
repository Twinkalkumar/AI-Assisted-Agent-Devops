"""Unified approval workflow for MEDIUM/HIGH risk findings.

Three channels — CLI, file, and webhook — all read/write the same
JSON-backed store (state/approvals.json) so `main.py apply` doesn't
need to know which channel was used to approve a finding.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from risk_classifier import ClassifiedFinding

logger = logging.getLogger("costguard.approval")

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
APPROVALS_PATH = STATE_DIR / "approvals.json"


@dataclass
class ApprovalRecord:
    finding_id: str
    status: str  # "pending" | "approved" | "denied"
    approved_by: str | None = None
    timestamp: str | None = None


class ApprovalStore:
    """Loads/saves state/approvals.json — a finding_id -> ApprovalRecord map."""

    def __init__(self, path: Path = APPROVALS_PATH) -> None:
        self._path = path
        self._records: dict[str, ApprovalRecord] = self._load()

    def _load(self) -> dict[str, ApprovalRecord]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return {k: ApprovalRecord(**v) for k, v in raw.items()}

    def _save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        raw = {k: vars(v) for k, v in self._records.items()}
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2)

    def get(self, finding_id: str) -> ApprovalRecord | None:
        return self._records.get(finding_id)

    def is_approved(self, finding_id: str) -> bool:
        record = self._records.get(finding_id)
        return record is not None and record.status == "approved"

    def ensure_pending(self, finding_id: str) -> ApprovalRecord:
        """Create a pending record if one doesn't already exist, without
        overwriting an existing decision. This is what keeps `plan` runs
        idempotent — re-planning never resets an already-approved/denied
        finding back to pending.
        """
        if finding_id not in self._records:
            self._records[finding_id] = ApprovalRecord(finding_id=finding_id, status="pending")
            self._save()
        return self._records[finding_id]

    def record_decision(self, finding_id: str, status: str, approved_by: str) -> None:
        self._records[finding_id] = ApprovalRecord(
            finding_id=finding_id,
            status=status,
            approved_by=approved_by,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._save()


def request_cli_approval(classified: "ClassifiedFinding", store: ApprovalStore) -> bool:
    """Interactively prompt on the terminal; records and returns the decision."""
    f = classified.finding
    print(f"\n[{classified.risk.value}] {f.provider}/{f.account} {f.resource_id} — {f.action_type}")
    print(f"  {f.description}")
    print(f"  estimated monthly savings: ${f.estimated_monthly_savings_usd:.2f}")
    for reason in classified.reasons:
        print(f"  reason: {reason}")
    answer = input("  approve this action? [y/N] ").strip().lower()
    approved = answer in ("y", "yes")
    store.record_decision(f.id, "approved" if approved else "denied", approved_by="cli:interactive")
    return approved


def register_file_approval_request(classified: "ClassifiedFinding", store: ApprovalStore) -> None:
    """Ensure a pending entry exists in state/approvals.json for a human to
    edit out-of-band (flip "status" to "approved"/"denied" and re-run apply).
    """
    store.ensure_pending(classified.finding.id)


def send_webhook_approval_request(
    classified: "ClassifiedFinding", store: ApprovalStore, webhook_url: str
) -> None:
    """Notify an external system (e.g. Slack incoming webhook) and register
    a pending entry. The actual approval decision must be written back into
    state/approvals.json by whatever handles the webhook callback — this
    function only sends the notification and ensures the pending record
    exists so `apply` can pick it up once approved.
    """
    store.ensure_pending(classified.finding.id)
    f = classified.finding
    payload = {
        "text": (
            f"[CostGuard] approval requested: {classified.risk.value} risk — "
            f"{f.provider}/{f.account} {f.resource_id} ({f.action_type}), "
            f"est. savings ${f.estimated_monthly_savings_usd:.2f}/mo. "
            f"finding_id={f.id}"
        )
    }
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:  # noqa: BLE001 - a failed notification shouldn't crash apply
        logger.warning("approval: failed to send webhook notification for %s: %s", f.id, exc)

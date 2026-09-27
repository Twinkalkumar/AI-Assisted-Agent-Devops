"""Executes findings (LOW-risk auto, or approved MEDIUM/HIGH) and rolls
them back. Every execution is recorded to the audit log and its
RollbackRecord persisted to state/rollback_records.json so a later
`main.py rollback <finding_id>` can reverse it — including in a
different process invocation than the one that executed it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import audit_log
from providers.base import CloudProvider, ProviderError, RollbackRecord
from risk_classifier import RiskLevel

if TYPE_CHECKING:
    from approval import ApprovalStore
    from risk_classifier import ClassifiedFinding

logger = logging.getLogger("costguard.executor")

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
ROLLBACK_RECORDS_PATH = STATE_DIR / "rollback_records.json"


def _load_rollback_records() -> dict[str, dict]:
    if not ROLLBACK_RECORDS_PATH.exists():
        return {}
    with ROLLBACK_RECORDS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _persist_rollback_record(record: RollbackRecord) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    records = _load_rollback_records()
    records[record.finding_id] = vars(record)
    with ROLLBACK_RECORDS_PATH.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def _mark_rolled_back(finding_id: str) -> None:
    records = _load_rollback_records()
    if finding_id in records:
        records[finding_id]["rolled_back"] = True
        with ROLLBACK_RECORDS_PATH.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)


def _execute_one(
    classified: "ClassifiedFinding",
    providers: dict[str, CloudProvider],
    approved_by: str,
) -> bool:
    finding = classified.finding
    provider = providers.get(finding.provider)
    if provider is None:
        logger.warning("executor: no provider adapter registered for %r — skipping %s", finding.provider, finding.id)
        return False

    try:
        record = provider.execute_action(finding)
    except NotImplementedError as exc:
        logger.warning("executor: %s not supported yet for %s — skipping", finding.action_type, finding.id)
        return False
    except ProviderError as exc:
        audit_log.record_audit_event(
            event_type="execution_failed",
            finding_id=finding.id,
            provider=finding.provider,
            account=finding.account,
            resource_id=finding.resource_id,
            action_type=finding.action_type,
            approved_by=approved_by,
            rollback_command="",
            details={"error": str(exc)},
        )
        logger.error("executor: failed to execute %s: %s", finding.id, exc)
        return False

    _persist_rollback_record(record)
    rollback_command = f"python src/main.py rollback {finding.id}"
    audit_log.record_audit_event(
        event_type="executed",
        finding_id=finding.id,
        provider=finding.provider,
        account=finding.account,
        resource_id=finding.resource_id,
        action_type=finding.action_type,
        approved_by=approved_by,
        rollback_command=rollback_command,
        details={
            "estimated_monthly_savings_usd": finding.estimated_monthly_savings_usd,
            "rollback_note": record.rollback_note,
        },
    )
    return True


def apply_low_risk(
    classified_findings: list["ClassifiedFinding"],
    providers: dict[str, CloudProvider],
    max_auto_actions_per_run: int,
) -> list[str]:
    """Auto-execute LOW-risk, auto_executable findings, capped at
    `max_auto_actions_per_run` (the blast-radius limit). Returns the list
    of finding ids that were executed.
    """
    executed: list[str] = []
    for classified in classified_findings:
        if len(executed) >= max_auto_actions_per_run:
            logger.info("executor: blast-radius cap (%d) reached — stopping auto-execution", max_auto_actions_per_run)
            break
        # Defense in depth: re-check the hard gate here too, independent of
        # whatever set auto_executable, so a bug elsewhere can't cause an
        # auto-execute path to touch anything but LOW-risk, tagged,
        # non-production resources.
        if not classified.auto_executable or classified.risk != RiskLevel.LOW:
            continue
        if _execute_one(classified, providers, approved_by="auto (LOW risk)"):
            executed.append(classified.finding.id)
    return executed


def apply_approved(
    classified_findings: list["ClassifiedFinding"],
    providers: dict[str, CloudProvider],
    approval_store: "ApprovalStore",
) -> list[str]:
    """Execute MEDIUM/HIGH findings that have an "approved" record in the
    approval store. Never executes anything auto_executable=True here —
    that path is apply_low_risk's job — so there's no overlap/double-exec.
    """
    executed: list[str] = []
    for classified in classified_findings:
        if classified.auto_executable:
            continue
        record = approval_store.get(classified.finding.id)
        if record is None or record.status != "approved":
            continue
        approved_by = record.approved_by or "unknown"
        if _execute_one(classified, providers, approved_by=approved_by):
            executed.append(classified.finding.id)
    return executed


def rollback(finding_id: str, providers: dict[str, CloudProvider]) -> None:
    """Reverse a previously executed action using its persisted RollbackRecord."""
    records = _load_rollback_records()
    raw = records.get(finding_id)
    if raw is None:
        raise ProviderError(f"no rollback record found for finding {finding_id!r} — was it ever executed?")
    if raw.get("rolled_back"):
        raise ProviderError(f"finding {finding_id!r} has already been rolled back")

    record = RollbackRecord(
        finding_id=raw["finding_id"],
        provider=raw["provider"],
        account=raw["account"],
        resource_id=raw["resource_id"],
        action_type=raw["action_type"],
        rollback_data=raw["rollback_data"],
        rollback_note=raw.get("rollback_note", ""),
    )
    provider = providers.get(record.provider)
    if provider is None:
        raise ProviderError(f"no provider adapter registered for {record.provider!r}")

    provider.rollback_action(record)
    _mark_rolled_back(finding_id)
    audit_log.record_audit_event(
        event_type="rolled_back",
        finding_id=finding_id,
        provider=record.provider,
        account=record.account,
        resource_id=record.resource_id,
        action_type=record.action_type,
        approved_by="manual",
        rollback_command="",
        details={"rollback_data": record.rollback_data},
    )

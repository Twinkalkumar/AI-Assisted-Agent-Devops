"""Assigns a LOW/MEDIUM/HIGH risk score to every finding.

The rule "never auto-act on production-tagged or completely untagged
resources" is enforced here in code (`_is_untagged` / `_is_prod` checks
gating `auto_executable`), not via config — thresholds.yaml and
tag_policy.yaml can change *what counts* as prod/critical, but cannot
disable the gate itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from recommender import Finding


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# Base risk per action type, before tag-based escalation. Unknown/future
# action types default to HIGH (fail safe) via BASE_RISK_BY_ACTION.get(...).
BASE_RISK_BY_ACTION: dict[str, RiskLevel] = {
    "delete_orphaned_volume": RiskLevel.LOW,
    "delete_unused_eip": RiskLevel.LOW,
    "stop_idle_instance": RiskLevel.LOW,
    "downsize_instance": RiskLevel.MEDIUM,
    "switch_to_spot": RiskLevel.MEDIUM,
    "resize_database": RiskLevel.HIGH,
    "migrate_region": RiskLevel.HIGH,
}


@dataclass
class ClassifiedFinding:
    """A Finding plus its assigned risk level and the reasons behind it."""

    finding: "Finding"
    risk: RiskLevel
    reasons: list[str] = field(default_factory=list)
    auto_executable: bool = False


def _is_untagged(tags: dict[str, str]) -> bool:
    return not tags


def _matches_any(tags: dict[str, str], keys: list[str], values: set[str]) -> bool:
    for key in keys:
        if str(tags.get(key, "")).strip().lower() in values:
            return True
    return False


def is_prod(tags: dict[str, str], tag_policy: dict) -> bool:
    """True if any configured env tag key holds a configured prod value."""
    keys = tag_policy.get("env_tag_keys", ["env"])
    values = {v.lower() for v in tag_policy.get("prod_values", ["prod", "production"])}
    return _matches_any(tags, keys, values)


def is_dev_or_test(tags: dict[str, str], tag_policy: dict) -> bool:
    """True if any configured env tag key holds a configured dev/test value."""
    keys = tag_policy.get("env_tag_keys", ["env"])
    values = {
        v.lower()
        for v in [*tag_policy.get("dev_values", []), *tag_policy.get("test_values", [])]
    }
    return _matches_any(tags, keys, values)


def is_critical(tags: dict[str, str], tag_policy: dict) -> bool:
    """True if any configured critical tag key holds a configured truthy value."""
    keys = tag_policy.get("critical_tag_keys", ["critical"])
    values = {v.lower() for v in tag_policy.get("critical_values", ["true", "yes"])}
    return _matches_any(tags, keys, values)


def classify(finding: "Finding", tag_policy: dict) -> ClassifiedFinding:
    """Assign a risk level to `finding` and decide if it's safe to auto-execute."""
    reasons: list[str] = []
    tags = finding.tags

    base_risk = BASE_RISK_BY_ACTION.get(finding.action_type, RiskLevel.HIGH)
    reasons.append(f"base risk for action '{finding.action_type}' is {base_risk.value}")
    risk = base_risk

    untagged = _is_untagged(tags)
    prod = is_prod(tags, tag_policy)
    critical = is_critical(tags, tag_policy)

    if untagged:
        risk = RiskLevel.HIGH
        reasons.append("resource has no tags — untagged resources always require approval")
    elif prod:
        risk = RiskLevel.HIGH
        reasons.append("resource is tagged as production — always requires approval")
    elif critical:
        risk = RiskLevel.HIGH
        reasons.append("resource is tagged critical=true — always requires approval")

    # Defense in depth: stop_idle_instance is only ever LOW risk for
    # dev/test resources. If it somehow reaches here for anything else,
    # escalate rather than trust the base table.
    if (
        finding.action_type == "stop_idle_instance"
        and not untagged
        and not prod
        and not is_dev_or_test(tags, tag_policy)
        and risk == RiskLevel.LOW
    ):
        risk = RiskLevel.MEDIUM
        reasons.append("stop_idle_instance proposed for a non-dev/test resource — escalated")

    # Hard, non-configurable gate: only LOW-risk actions on tagged,
    # non-production resources are ever auto-executable.
    auto_executable = risk == RiskLevel.LOW and not untagged and not prod

    return ClassifiedFinding(finding=finding, risk=risk, reasons=reasons, auto_executable=auto_executable)


def classify_all(findings: list["Finding"], tag_policy: dict) -> list[ClassifiedFinding]:
    """Classify a batch of findings."""
    return [classify(f, tag_policy) for f in findings]

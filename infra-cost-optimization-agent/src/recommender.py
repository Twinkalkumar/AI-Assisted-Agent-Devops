"""Turns utilization metrics into cost-saving findings.

Each finding proposes exactly one action for one resource. Findings are
never generated for resources the dead-man's switch has flagged as
having insufficient data (see ResourceMetrics.insufficient_data) — we
skip rather than guess.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from providers.base import ResourceMetrics

# Flat AWS list price for an unassociated Elastic IP (illustrative constant;
# real deployments should pull this from the Price List API).
UNUSED_EIP_MONTHLY_COST_USD = 3.60


@dataclass
class Finding:
    """One proposed cost-saving action for one resource."""

    id: str
    provider: str
    account: str
    resource_id: str
    resource_type: str
    action_type: str
    description: str
    tags: dict[str, str]
    current_state: dict = field(default_factory=dict)
    estimated_monthly_savings_usd: float = 0.0


@dataclass
class SkippedResource:
    """A resource the recommender deliberately did not propose an action for."""

    resource_id: str
    reason: str


def _finding_id(provider: str, account: str, resource_id: str, action_type: str) -> str:
    """Deterministic id so the same resource+action always maps to the same
    finding across runs — this is what makes repeated `plan` runs idempotent.
    """
    raw = f"{provider}:{account}:{resource_id}:{action_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _outside_business_hours(thresholds: dict) -> bool:
    """True if "now" (in the configured timezone) falls outside the
    configured business-hours window.
    """
    bh = thresholds.get("business_hours", {})
    tz = ZoneInfo(bh.get("timezone", "UTC"))
    now = datetime.now(tz)
    start_hour = bh.get("start_hour", 8)
    end_hour = bh.get("end_hour", 19)
    return not (start_hour <= now.hour < end_hour)


def _make_finding(
    metric: ResourceMetrics,
    action_type: str,
    description: str,
    savings_usd: float,
    current_state: dict,
) -> Finding:
    return Finding(
        id=_finding_id(metric.provider, metric.account, metric.resource_id, action_type),
        provider=metric.provider,
        account=metric.account,
        resource_id=metric.resource_id,
        resource_type=metric.resource_type,
        action_type=action_type,
        description=description,
        tags=dict(metric.tags),
        current_state=current_state,
        estimated_monthly_savings_usd=round(savings_usd, 2),
    )


def recommend(
    metrics: list[ResourceMetrics],
    thresholds: dict,
    tag_policy: dict,
) -> tuple[list[Finding], list[SkippedResource]]:
    """Compute findings + skipped resources for a batch of utilization data."""
    from risk_classifier import is_dev_or_test  # local import avoids a cycle at module load

    idle_cpu = thresholds["idle_cpu_pct_threshold"]
    orphaned_min_days = thresholds["orphaned_volume_min_days"]
    downsize_factor = thresholds.get("downsize_savings_factor", 0.5)

    findings: list[Finding] = []
    skipped: list[SkippedResource] = []

    for m in metrics:
        if m.insufficient_data:
            skipped.append(
                SkippedResource(
                    m.resource_id,
                    f"insufficient utilization data ({m.data_points}/{m.expected_data_points} "
                    "expected samples) — dead-man's switch skipped this resource",
                )
            )
            continue

        if m.resource_type == "ebs_volume":
            if m.attached is False and m.age_days >= orphaned_min_days:
                findings.append(
                    _make_finding(
                        m,
                        "delete_orphaned_volume",
                        f"Volume {m.resource_id} has been unattached for "
                        f"{m.age_days:.0f} days — delete it (snapshot first).",
                        savings_usd=m.monthly_cost_usd or 0.0,
                        current_state={"volume_id": m.resource_id, "region": m.region},
                    )
                )
            continue

        if m.resource_type == "elastic_ip":
            if m.attached is False:
                findings.append(
                    _make_finding(
                        m,
                        "delete_unused_eip",
                        f"Elastic IP {m.resource_id} is not associated with any instance.",
                        savings_usd=UNUSED_EIP_MONTHLY_COST_USD,
                        current_state={"allocation_id": m.resource_id, "region": m.region},
                    )
                )
            continue

        if m.resource_type == "ec2_instance":
            if m.state == "running" and m.avg_cpu_pct is not None and m.avg_cpu_pct < idle_cpu:
                if is_dev_or_test(m.tags, tag_policy) and _outside_business_hours(thresholds):
                    findings.append(
                        _make_finding(
                            m,
                            "stop_idle_instance",
                            f"Instance {m.resource_id} (env=dev/test) is idle "
                            f"({m.avg_cpu_pct:.1f}% avg CPU) outside business hours — stop it.",
                            savings_usd=m.monthly_cost_usd or 0.0,
                            current_state={
                                "instance_id": m.resource_id,
                                "region": m.region,
                                "previous_state": m.state,
                            },
                        )
                    )
                else:
                    findings.append(
                        _make_finding(
                            m,
                            "downsize_instance",
                            f"Instance {m.resource_id} ({m.instance_type}) is averaging "
                            f"{m.avg_cpu_pct:.1f}% CPU over {m.lookback_days} days — downsize one tier.",
                            savings_usd=(m.monthly_cost_usd or 0.0) * downsize_factor,
                            current_state={
                                "instance_id": m.resource_id,
                                "region": m.region,
                                "previous_instance_type": m.instance_type,
                            },
                        )
                    )
            continue

        if m.resource_type == "rds_instance":
            if m.state == "available" and m.avg_cpu_pct is not None and m.avg_cpu_pct < idle_cpu:
                findings.append(
                    _make_finding(
                        m,
                        "resize_database",
                        f"RDS instance {m.resource_id} ({m.instance_type}) is averaging "
                        f"{m.avg_cpu_pct:.1f}% CPU over {m.lookback_days} days — resize down.",
                        savings_usd=(m.monthly_cost_usd or 0.0) * downsize_factor,
                        current_state={
                            "db_instance_id": m.resource_id,
                            "region": m.region,
                            "previous_instance_class": m.instance_type,
                        },
                    )
                )
            continue

    return findings, skipped

"""Unit tests for recommender.py — mocked ResourceMetrics only, no live
cloud calls of any kind.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from providers.base import ResourceMetrics  # noqa: E402
from recommender import recommend  # noqa: E402

TAG_POLICY = {
    "env_tag_keys": ["env"],
    "prod_values": ["prod", "production"],
    "dev_values": ["dev", "development"],
    "test_values": ["test", "staging", "qa"],
    "critical_tag_keys": ["critical"],
    "critical_values": ["true", "yes"],
}

BASE_THRESHOLDS = {
    "idle_cpu_pct_threshold": 10.0,
    "orphaned_volume_min_days": 7,
    "downsize_savings_factor": 0.5,
    "business_hours": {"start_hour": 8, "end_hour": 19, "timezone": "UTC"},
}

# Deterministically "always outside business hours" regardless of wall clock.
ALWAYS_OUTSIDE_BUSINESS_HOURS = {
    **BASE_THRESHOLDS,
    "business_hours": {"start_hour": 0, "end_hour": 0, "timezone": "UTC"},
}


def _volume(attached: bool, age_days: float, tags: dict | None = None) -> ResourceMetrics:
    return ResourceMetrics(
        provider="aws",
        account="example-aws-account",
        resource_id="vol-1",
        resource_type="ebs_volume",
        region="us-east-1",
        state="available" if not attached else "in-use",
        tags=tags or {"env": "dev"},
        attached=attached,
        age_days=age_days,
        monthly_cost_usd=8.0,
        data_points=1,
        expected_data_points=1,
    )


def _eip(attached: bool) -> ResourceMetrics:
    return ResourceMetrics(
        provider="aws",
        account="example-aws-account",
        resource_id="eipalloc-1",
        resource_type="elastic_ip",
        region="us-east-1",
        state="associated" if attached else "unassociated",
        tags={"env": "dev"},
        attached=attached,
        monthly_cost_usd=0.0 if attached else 3.60,
        data_points=1,
        expected_data_points=1,
    )


def _ec2_instance(avg_cpu: float, tags: dict, data_points=336, expected_data_points=336) -> ResourceMetrics:
    return ResourceMetrics(
        provider="aws",
        account="example-aws-account",
        resource_id="i-1",
        resource_type="ec2_instance",
        region="us-east-1",
        state="running",
        tags=tags,
        instance_type="t3.large",
        monthly_cost_usd=60.0,
        avg_cpu_pct=avg_cpu,
        max_cpu_pct=avg_cpu + 5,
        lookback_days=14,
        data_points=data_points,
        expected_data_points=expected_data_points,
    )


def _rds_instance(avg_cpu: float, data_points=336, expected_data_points=336) -> ResourceMetrics:
    return ResourceMetrics(
        provider="aws",
        account="example-aws-account",
        resource_id="db-1",
        resource_type="rds_instance",
        region="us-east-1",
        state="available",
        tags={"env": "dev"},
        instance_type="db.t3.medium",
        monthly_cost_usd=100.0,
        avg_cpu_pct=avg_cpu,
        max_cpu_pct=avg_cpu + 5,
        lookback_days=14,
        data_points=data_points,
        expected_data_points=expected_data_points,
    )


def test_insufficient_data_resource_is_skipped_not_guessed_about():
    metric = _ec2_instance(avg_cpu=1.0, tags={"env": "dev"}, data_points=10, expected_data_points=336)
    findings, skipped = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert findings == []
    assert len(skipped) == 1
    assert skipped[0].resource_id == "i-1"


def test_orphaned_volume_past_min_age_is_flagged():
    metric = _volume(attached=False, age_days=10)
    findings, skipped = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert len(findings) == 1
    assert findings[0].action_type == "delete_orphaned_volume"
    assert findings[0].estimated_monthly_savings_usd == 8.0


def test_recently_unattached_volume_is_not_flagged_yet():
    metric = _volume(attached=False, age_days=2)
    findings, skipped = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert findings == []


def test_attached_volume_is_never_flagged():
    metric = _volume(attached=True, age_days=100)
    findings, skipped = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert findings == []


def test_unassociated_elastic_ip_is_flagged():
    metric = _eip(attached=False)
    findings, skipped = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert len(findings) == 1
    assert findings[0].action_type == "delete_unused_eip"


def test_associated_elastic_ip_is_never_flagged():
    metric = _eip(attached=True)
    findings, skipped = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert findings == []


def test_idle_dev_instance_outside_business_hours_is_stopped_not_downsized():
    metric = _ec2_instance(avg_cpu=2.0, tags={"env": "dev"})
    findings, _ = recommend([metric], ALWAYS_OUTSIDE_BUSINESS_HOURS, TAG_POLICY)
    assert len(findings) == 1
    assert findings[0].action_type == "stop_idle_instance"


def test_idle_non_dev_instance_is_downsized_not_stopped():
    metric = _ec2_instance(avg_cpu=2.0, tags={"env": "prod"})
    findings, _ = recommend([metric], ALWAYS_OUTSIDE_BUSINESS_HOURS, TAG_POLICY)
    assert len(findings) == 1
    assert findings[0].action_type == "downsize_instance"
    assert findings[0].estimated_monthly_savings_usd == 30.0  # 60.0 * downsize_savings_factor


def test_busy_instance_is_never_flagged():
    metric = _ec2_instance(avg_cpu=75.0, tags={"env": "dev"})
    findings, _ = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert findings == []


def test_idle_rds_instance_is_flagged_for_resize():
    metric = _rds_instance(avg_cpu=3.0)
    findings, _ = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert len(findings) == 1
    assert findings[0].action_type == "resize_database"


def test_finding_ids_are_deterministic_across_repeated_runs():
    metric = _volume(attached=False, age_days=10)
    findings_1, _ = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    findings_2, _ = recommend([metric], BASE_THRESHOLDS, TAG_POLICY)
    assert findings_1[0].id == findings_2[0].id

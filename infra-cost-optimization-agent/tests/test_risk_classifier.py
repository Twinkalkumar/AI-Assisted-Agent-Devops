"""Unit tests for risk_classifier.py — no live cloud calls.

The critical property under test: prod-tagged or completely untagged
resources are NEVER auto_executable, regardless of the action's base
risk or anything else about the finding.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from recommender import Finding  # noqa: E402
from risk_classifier import RiskLevel, classify  # noqa: E402

TAG_POLICY = {
    "env_tag_keys": ["env"],
    "prod_values": ["prod", "production"],
    "dev_values": ["dev", "development"],
    "test_values": ["test", "staging", "qa"],
    "critical_tag_keys": ["critical"],
    "critical_values": ["true", "yes"],
}


def _finding(action_type: str, tags: dict[str, str]) -> Finding:
    return Finding(
        id="abc123",
        provider="aws",
        account="example-aws-account",
        resource_id="vol-0123456789",
        resource_type="ebs_volume",
        action_type=action_type,
        description="test finding",
        tags=tags,
        current_state={},
        estimated_monthly_savings_usd=10.0,
    )


def test_low_risk_action_on_untagged_resource_is_never_auto_executable():
    finding = _finding("delete_orphaned_volume", tags={})
    result = classify(finding, TAG_POLICY)
    assert result.risk == RiskLevel.HIGH
    assert result.auto_executable is False


def test_low_risk_action_on_prod_resource_is_never_auto_executable():
    finding = _finding("delete_orphaned_volume", tags={"env": "prod"})
    result = classify(finding, TAG_POLICY)
    assert result.risk == RiskLevel.HIGH
    assert result.auto_executable is False


def test_low_risk_action_on_critical_resource_is_never_auto_executable():
    finding = _finding("delete_orphaned_volume", tags={"env": "dev", "critical": "true"})
    result = classify(finding, TAG_POLICY)
    assert result.risk == RiskLevel.HIGH
    assert result.auto_executable is False


def test_low_risk_action_on_tagged_dev_resource_is_auto_executable():
    finding = _finding("delete_orphaned_volume", tags={"env": "dev"})
    result = classify(finding, TAG_POLICY)
    assert result.risk == RiskLevel.LOW
    assert result.auto_executable is True


def test_medium_risk_action_is_never_auto_executable_even_when_tagged_dev():
    finding = _finding("downsize_instance", tags={"env": "dev"})
    result = classify(finding, TAG_POLICY)
    assert result.risk == RiskLevel.MEDIUM
    assert result.auto_executable is False


def test_high_risk_action_is_never_auto_executable():
    finding = _finding("resize_database", tags={"env": "dev"})
    result = classify(finding, TAG_POLICY)
    assert result.risk == RiskLevel.HIGH
    assert result.auto_executable is False


def test_stop_idle_instance_escalates_to_medium_for_non_dev_test_tagged_resource():
    # Defense in depth: recommender should never propose stop_idle_instance
    # outside dev/test, but if it ever does, risk_classifier must not
    # trust the LOW base risk blindly.
    finding = _finding("stop_idle_instance", tags={"team": "platform"})
    result = classify(finding, TAG_POLICY)
    assert result.risk == RiskLevel.MEDIUM
    assert result.auto_executable is False


def test_unknown_action_type_defaults_to_high_risk():
    finding = _finding("some_future_action_type", tags={"env": "dev"})
    result = classify(finding, TAG_POLICY)
    assert result.risk == RiskLevel.HIGH
    assert result.auto_executable is False

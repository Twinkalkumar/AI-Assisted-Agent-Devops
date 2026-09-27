"""Loads config, builds provider adapters, and aggregates utilization data
across every enabled provider/account.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from providers.aws_provider import AWSProvider
from providers.azure_provider import AzureProvider
from providers.base import CloudProvider, ResourceMetrics
from providers.gcp_provider import GCPProvider

logger = logging.getLogger("costguard.analyzer")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Registering a new provider here (and adding its adapter file under
# providers/) is the only place outside the adapter itself that needs
# to change to support a new cloud.
_PROVIDER_CLASSES: dict[str, type[CloudProvider]] = {
    "aws": AWSProvider,
    "azure": AzureProvider,
    "gcp": GCPProvider,
}

_ACCOUNTS_KEY_BY_PROVIDER = {
    "aws": "accounts",
    "azure": "subscriptions",
    "gcp": "projects",
}


def load_yaml(name: str) -> dict:
    """Load a YAML file from config/ by filename."""
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_providers(providers_cfg: dict) -> dict[str, CloudProvider]:
    """Instantiate one adapter per enabled provider, each pre-loaded with
    its configured accounts so execute_action/rollback_action can resolve
    credentials later without re-reading config.
    """
    providers: dict[str, CloudProvider] = {}
    for key, cls in _PROVIDER_CLASSES.items():
        cfg = providers_cfg.get(key, {})
        if not cfg.get("enabled", False):
            continue
        accounts = cfg.get(_ACCOUNTS_KEY_BY_PROVIDER[key], [])
        adapter = cls(accounts=accounts)
        if not adapter.is_available():
            logger.warning("provider %s is enabled in config but not available (SDK missing?) — skipping", key)
            continue
        providers[key] = adapter
    return providers


def collect_metrics(
    providers: dict[str, CloudProvider],
    providers_cfg: dict,
    thresholds: dict,
) -> list[ResourceMetrics]:
    """Call list_resources for every enabled provider/account and return the
    combined set of ResourceMetrics. A single account/provider failure never
    aborts the whole collection — see each adapter's own error handling.
    """
    lookback_days = thresholds.get("lookback_days", 14)
    all_metrics: list[ResourceMetrics] = []

    for key, adapter in providers.items():
        accounts = providers_cfg.get(key, {}).get(_ACCOUNTS_KEY_BY_PROVIDER[key], [])
        for account in accounts:
            account = {**account, "lookback_days": lookback_days}
            try:
                all_metrics.extend(adapter.list_resources(account))
            except Exception as exc:  # noqa: BLE001 - one account failing shouldn't abort the run
                logger.warning(
                    "analyzer: list_resources failed for provider=%s account=%s: %s",
                    key,
                    account.get("name"),
                    exc,
                )

    return all_metrics


def analyze() -> tuple[list[ResourceMetrics], dict, dict, dict[str, CloudProvider], dict]:
    """Load all config, build providers, and collect metrics in one call.

    Returns (metrics, thresholds, tag_policy, providers, providers_cfg) so
    callers (main.py's plan/apply/rollback commands) can reuse the same
    provider instances rather than rebuilding them.
    """
    thresholds = load_yaml("thresholds.yaml")
    tag_policy = load_yaml("tag_policy.yaml")
    providers_cfg = load_yaml("providers.yaml")

    providers = build_providers(providers_cfg)
    metrics = collect_metrics(providers, providers_cfg, thresholds)

    return metrics, thresholds, tag_policy, providers, providers_cfg

"""Abstract interface every cloud provider adapter must implement.

Adding a new provider means creating one new file implementing
`CloudProvider` and registering it in `analyzer.py`'s provider registry —
nothing else in the codebase needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(Exception):
    """Raised when a provider call fails (auth, API error, network, etc.).

    Adapters must catch their SDK-specific exceptions and re-raise as
    this common type so callers never need provider-specific except
    clauses, and a single provider outage never crashes the whole run.
    """


@dataclass
class ResourceMetrics:
    """One cloud resource plus its utilization over the lookback window."""

    provider: str
    account: str
    resource_id: str
    resource_type: str  # "ec2_instance" | "ebs_volume" | "elastic_ip" | "rds_instance" | ...
    region: str
    state: str  # e.g. "running", "stopped", "available", "in-use"
    tags: dict[str, str] = field(default_factory=dict)

    instance_type: str | None = None  # current size/tier, if applicable
    attached: bool | None = None  # for volumes/EIPs: whether attached/associated
    age_days: float = 0.0
    monthly_cost_usd: float | None = None

    avg_cpu_pct: float | None = None
    max_cpu_pct: float | None = None

    lookback_days: int = 14
    data_points: int = 0
    expected_data_points: int = 0

    @property
    def insufficient_data(self) -> bool:
        """True if too few metric samples were returned to trust a
        recommendation (dead-man's switch) — e.g. a metrics gap, or the
        resource is younger than the lookback window.
        """
        if self.expected_data_points <= 0:
            return False
        return (self.data_points / self.expected_data_points) < 0.6


@dataclass
class RollbackRecord:
    """Everything needed to reverse a previously executed action."""

    finding_id: str
    provider: str
    account: str
    resource_id: str
    action_type: str
    rollback_data: dict
    rollback_note: str = ""


class CloudProvider(ABC):
    """Common interface for AWS/Azure/GCP (and future) adapters."""

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider's SDK is installed and usable."""

    @abstractmethod
    def list_resources(self, account: dict) -> list[ResourceMetrics]:
        """Return utilization-enriched resources for one configured account.

        Must not raise on a partial failure (e.g. one API call failing) —
        log and skip that resource type, returning whatever was collected.
        """

    @abstractmethod
    def execute_action(self, finding: "Finding") -> RollbackRecord:  # noqa: F821 - see recommender.Finding
        """Execute the action described by `finding`; return rollback data.

        Must raise NotImplementedError (not crash) for action types this
        provider doesn't yet support, and ProviderError for a failed call.
        """

    @abstractmethod
    def rollback_action(self, record: RollbackRecord) -> None:
        """Reverse a previously executed action using its RollbackRecord."""

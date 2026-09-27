"""GCP provider adapter — stub.

Interface parity with AWSProvider is intentional: analyzer.py and
executor.py never need to know which provider they're talking to.
Full implementation (Compute Engine, Persistent Disks, Cloud SQL) is
out of scope for this pass — see the TODOs below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from providers.base import CloudProvider, ResourceMetrics, RollbackRecord

if TYPE_CHECKING:
    from recommender import Finding


class GCPProvider(CloudProvider):
    """CloudProvider adapter for GCP (Compute Engine, Persistent Disks, Cloud SQL)."""

    name = "gcp"

    def __init__(self, accounts: list[dict] | None = None) -> None:
        self._accounts: dict[str, dict] = {a["name"]: a for a in (accounts or [])}

    def is_available(self) -> bool:
        # TODO: implement — return True once google-cloud-compute is wired up
        # and Application Default Credentials can be obtained.
        return False

    def list_resources(self, account: dict) -> list[ResourceMetrics]:
        # TODO: implement — list Compute Engine instances, Persistent Disks,
        # and Cloud SQL instances for `account["project_id"]`, enriching
        # each with Cloud Monitoring metrics (compute.googleapis.com/instance/
        # cpu/utilization) the same way aws_provider.py uses CloudWatch,
        # populating data_points/expected_data_points for the dead-man's switch.
        raise NotImplementedError("gcp_provider.list_resources is not implemented yet")

    def execute_action(self, finding: "Finding") -> RollbackRecord:
        # TODO: implement action handlers (stop instance, resize machine
        # type, delete unattached disk, resize Cloud SQL instance) mirroring
        # aws_provider.py's _execute_* dispatch pattern.
        raise NotImplementedError("gcp_provider.execute_action is not implemented yet")

    def rollback_action(self, record: RollbackRecord) -> None:
        # TODO: implement matching _rollback_* handlers for each action type.
        raise NotImplementedError("gcp_provider.rollback_action is not implemented yet")

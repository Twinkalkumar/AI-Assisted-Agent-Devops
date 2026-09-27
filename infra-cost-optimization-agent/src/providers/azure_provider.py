"""Azure provider adapter — stub.

Interface parity with AWSProvider is intentional: analyzer.py and
executor.py never need to know which provider they're talking to.
Full implementation (VMs, Managed Disks, SQL Database) is out of
scope for this pass — see the TODOs below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from providers.base import CloudProvider, ResourceMetrics, RollbackRecord

if TYPE_CHECKING:
    from recommender import Finding


class AzureProvider(CloudProvider):
    """CloudProvider adapter for Azure (VMs, Managed Disks, SQL Database)."""

    name = "azure"

    def __init__(self, accounts: list[dict] | None = None) -> None:
        self._accounts: dict[str, dict] = {a["name"]: a for a in (accounts or [])}

    def is_available(self) -> bool:
        # TODO: implement — return True once azure-identity/azure-mgmt-compute
        # are wired up and a credential can be obtained (DefaultAzureCredential).
        return False

    def list_resources(self, account: dict) -> list[ResourceMetrics]:
        # TODO: implement — list VMs (azure-mgmt-compute), Managed Disks, and
        # SQL Database instances for `account["subscription_id"]`, enriching
        # each with Azure Monitor metrics (Percentage CPU) the same way
        # aws_provider.py uses CloudWatch, populating data_points/
        # expected_data_points for the dead-man's switch.
        raise NotImplementedError("azure_provider.list_resources is not implemented yet")

    def execute_action(self, finding: "Finding") -> RollbackRecord:
        # TODO: implement action handlers (deallocate VM, resize VM, delete
        # unattached disk, resize SQL Database) mirroring aws_provider.py's
        # _execute_* dispatch pattern.
        raise NotImplementedError("azure_provider.execute_action is not implemented yet")

    def rollback_action(self, record: RollbackRecord) -> None:
        # TODO: implement matching _rollback_* handlers for each action type.
        raise NotImplementedError("azure_provider.rollback_action is not implemented yet")

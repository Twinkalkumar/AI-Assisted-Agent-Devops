"""AWS provider adapter — EC2, EBS, Elastic IPs, RDS.

Credentials come entirely from boto3's default credential chain (a
named profile via `account["profile"]`, environment variables, or an
instance role) — nothing is hardcoded here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from providers.base import CloudProvider, ProviderError, ResourceMetrics, RollbackRecord

if TYPE_CHECKING:
    from recommender import Finding

logger = logging.getLogger("costguard.aws")

# Illustrative on-demand pricing (USD/hour, approximate) used only to
# estimate savings shown in `plan` — not a live Price List API lookup.
EC2_HOURLY_USD = {
    "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416, "t3.large": 0.0832,
    "t3.xlarge": 0.1664, "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
    "c5.large": 0.085, "c5.xlarge": 0.17,
}
RDS_HOURLY_USD = {
    "db.t3.micro": 0.017, "db.t3.small": 0.034, "db.t3.medium": 0.068,
    "db.m5.large": 0.171, "db.m5.xlarge": 0.342,
    "db.r5.large": 0.24, "db.r5.xlarge": 0.48, "db.r5.2xlarge": 0.96,
}
EBS_GP3_USD_PER_GB_MONTH = 0.08
UNUSED_EIP_MONTHLY_COST_USD = 3.60
HOURS_PER_MONTH = 730
DEFAULT_UNKNOWN_INSTANCE_HOURLY_USD = 0.05

EC2_DOWNSIZE_MAP = {
    "t3.xlarge": "t3.large", "t3.large": "t3.medium", "t3.medium": "t3.small",
    "t3.small": "t3.micro", "m5.2xlarge": "m5.xlarge", "m5.xlarge": "m5.large",
    "c5.xlarge": "c5.large",
}
RDS_DOWNSIZE_MAP = {
    "db.r5.2xlarge": "db.r5.xlarge", "db.r5.xlarge": "db.r5.large",
    "db.m5.xlarge": "db.m5.large",
}


def _ec2_monthly_cost(instance_type: str) -> float:
    hourly = EC2_HOURLY_USD.get(instance_type, DEFAULT_UNKNOWN_INSTANCE_HOURLY_USD)
    return hourly * HOURS_PER_MONTH


def _rds_monthly_cost(instance_class: str) -> float:
    hourly = RDS_HOURLY_USD.get(instance_class, DEFAULT_UNKNOWN_INSTANCE_HOURLY_USD)
    return hourly * HOURS_PER_MONTH


class AWSProvider(CloudProvider):
    """CloudProvider adapter for AWS (EC2, EBS, Elastic IPs, RDS)."""

    name = "aws"

    def __init__(self, accounts: list[dict] | None = None) -> None:
        """`accounts` is the `aws.accounts` list from config/providers.yaml —
        stored so execute_action/rollback_action can resolve credentials
        for a finding/rollback record without re-reading config.
        """
        self._accounts: dict[str, dict] = {a["name"]: a for a in (accounts or [])}

    def is_available(self) -> bool:
        try:
            import boto3  # noqa: F401
        except ImportError:
            return False
        return True

    def _require_account(self, account_name: str) -> dict:
        account = self._accounts.get(account_name)
        if account is None:
            raise ProviderError(
                f"account {account_name!r} is not registered with this AWSProvider "
                "instance — construct it with the full accounts list from "
                "config/providers.yaml before calling execute_action/rollback_action"
            )
        return account

    def _session(self, account: dict):
        import boto3

        kwargs = {}
        if account.get("profile"):
            kwargs["profile_name"] = account["profile"]
        return boto3.Session(**kwargs)

    # -- analyze -----------------------------------------------------

    def list_resources(self, account: dict) -> list[ResourceMetrics]:
        self._accounts[account["name"]] = account
        try:
            session = self._session(account)
            region = account["region"]
            ec2 = session.client("ec2", region_name=region)
            rds = session.client("rds", region_name=region)
            cw = session.client("cloudwatch", region_name=region)
        except Exception as exc:  # noqa: BLE001 - normalize any SDK/auth error
            logger.warning("aws: could not create clients for account %s: %s", account.get("name"), exc)
            return []

        lookback_days = account.get("lookback_days", 14)
        resources: list[ResourceMetrics] = []
        for label, fn in (
            ("ec2 instances", lambda: self._list_ec2_instances(ec2, cw, account, lookback_days)),
            ("ebs volumes", lambda: self._list_ebs_volumes(ec2, account)),
            ("elastic ips", lambda: self._list_elastic_ips(ec2, account)),
            ("rds instances", lambda: self._list_rds_instances(rds, cw, account, lookback_days)),
        ):
            try:
                resources.extend(fn())
            except Exception as exc:  # noqa: BLE001 - one bad API call shouldn't kill the run
                logger.warning("aws: failed to list %s for account %s: %s", label, account.get("name"), exc)

        return resources

    def _cpu_stats(self, cw, namespace: str, dim_name: str, resource_id: str, lookback_days: int):
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        period = 3600
        resp = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName="CPUUtilization",
            Dimensions=[{"Name": dim_name, "Value": resource_id}],
            StartTime=start,
            EndTime=end,
            Period=period,
            Statistics=["Average", "Maximum"],
        )
        datapoints = resp.get("Datapoints", [])
        expected = max(1, int(lookback_days * 24 * 3600 / period))
        if not datapoints:
            return None, None, 0, expected
        avg = sum(d["Average"] for d in datapoints) / len(datapoints)
        mx = max(d["Maximum"] for d in datapoints)
        return avg, mx, len(datapoints), expected

    def _list_ec2_instances(self, ec2, cw, account, lookback_days) -> list[ResourceMetrics]:
        now = datetime.now(timezone.utc)
        results = []
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped"]}]
        ):
            for reservation in page["Reservations"]:
                for inst in reservation["Instances"]:
                    instance_id = inst["InstanceId"]
                    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                    age_days = (now - inst["LaunchTime"]).total_seconds() / 86400
                    avg_cpu, max_cpu, data_points, expected = self._cpu_stats(
                        cw, "AWS/EC2", "InstanceId", instance_id, lookback_days
                    )
                    results.append(
                        ResourceMetrics(
                            provider="aws",
                            account=account["name"],
                            resource_id=instance_id,
                            resource_type="ec2_instance",
                            region=account["region"],
                            state=inst["State"]["Name"],
                            tags=tags,
                            instance_type=inst["InstanceType"],
                            age_days=age_days,
                            monthly_cost_usd=_ec2_monthly_cost(inst["InstanceType"]),
                            avg_cpu_pct=avg_cpu,
                            max_cpu_pct=max_cpu,
                            lookback_days=lookback_days,
                            data_points=data_points,
                            expected_data_points=expected,
                        )
                    )
        return results

    def _list_ebs_volumes(self, ec2, account) -> list[ResourceMetrics]:
        now = datetime.now(timezone.utc)
        results = []
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for vol in page["Volumes"]:
                tags = {t["Key"]: t["Value"] for t in vol.get("Tags", [])}
                age_days = (now - vol["CreateTime"]).total_seconds() / 86400
                attached = len(vol.get("Attachments", [])) > 0
                results.append(
                    ResourceMetrics(
                        provider="aws",
                        account=account["name"],
                        resource_id=vol["VolumeId"],
                        resource_type="ebs_volume",
                        region=account["region"],
                        state=vol["State"],
                        tags=tags,
                        attached=attached,
                        age_days=age_days,
                        monthly_cost_usd=vol["Size"] * EBS_GP3_USD_PER_GB_MONTH,
                        # Attachment state is a point-in-time fact, not a metrics
                        # series, so there's no metrics-gap concept here.
                        data_points=1,
                        expected_data_points=1,
                    )
                )
        return results

    def _list_elastic_ips(self, ec2, account) -> list[ResourceMetrics]:
        resp = ec2.describe_addresses()
        results = []
        for addr in resp.get("Addresses", []):
            tags = {t["Key"]: t["Value"] for t in addr.get("Tags", [])}
            attached = "AssociationId" in addr
            allocation_id = addr.get("AllocationId", addr.get("PublicIp"))
            results.append(
                ResourceMetrics(
                    provider="aws",
                    account=account["name"],
                    resource_id=allocation_id,
                    resource_type="elastic_ip",
                    region=account["region"],
                    state="associated" if attached else "unassociated",
                    tags=tags,
                    attached=attached,
                    monthly_cost_usd=0.0 if attached else UNUSED_EIP_MONTHLY_COST_USD,
                    data_points=1,
                    expected_data_points=1,
                )
            )
        return results

    def _list_rds_instances(self, rds, cw, account, lookback_days) -> list[ResourceMetrics]:
        now = datetime.now(timezone.utc)
        results = []
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page["DBInstances"]:
                db_id = db["DBInstanceIdentifier"]
                try:
                    tag_resp = rds.list_tags_for_resource(ResourceName=db["DBInstanceArn"])
                    tags = {t["Key"]: t["Value"] for t in tag_resp.get("TagList", [])}
                except Exception:  # noqa: BLE001 - tags are best-effort
                    tags = {}
                age_days = (now - db["InstanceCreateTime"]).total_seconds() / 86400
                avg_cpu, max_cpu, data_points, expected = self._cpu_stats(
                    cw, "AWS/RDS", "DBInstanceIdentifier", db_id, lookback_days
                )
                results.append(
                    ResourceMetrics(
                        provider="aws",
                        account=account["name"],
                        resource_id=db_id,
                        resource_type="rds_instance",
                        region=account["region"],
                        state=db["DBInstanceStatus"],
                        tags=tags,
                        instance_type=db["DBInstanceClass"],
                        age_days=age_days,
                        monthly_cost_usd=_rds_monthly_cost(db["DBInstanceClass"]),
                        avg_cpu_pct=avg_cpu,
                        max_cpu_pct=max_cpu,
                        lookback_days=lookback_days,
                        data_points=data_points,
                        expected_data_points=expected,
                    )
                )
        return results

    # -- execute / rollback --------------------------------------------

    def execute_action(self, finding: "Finding") -> RollbackRecord:
        handler = getattr(self, f"_execute_{finding.action_type}", None)
        if handler is None:
            raise NotImplementedError(
                f"aws provider has no executor for action_type={finding.action_type!r} "
                "(TODO: not implemented in this pass — see README)"
            )
        return handler(finding)

    def rollback_action(self, record: RollbackRecord) -> None:
        handler = getattr(self, f"_rollback_{record.action_type}", None)
        if handler is None:
            raise NotImplementedError(f"aws provider has no rollback for action_type={record.action_type!r}")
        handler(record)

    def _execute_delete_orphaned_volume(self, finding: "Finding") -> RollbackRecord:
        account = self._require_account(finding.account)
        region = finding.current_state["region"]
        ec2 = self._session(account).client("ec2", region_name=region)
        volume_id = finding.current_state["volume_id"]
        try:
            vol = ec2.describe_volumes(VolumeIds=[volume_id])["Volumes"][0]
            az = vol["AvailabilityZone"]
            snap = ec2.create_snapshot(
                VolumeId=volume_id, Description=f"costguard pre-delete backup of {volume_id}"
            )
            ec2.get_waiter("snapshot_completed").wait(SnapshotIds=[snap["SnapshotId"]])
            ec2.delete_volume(VolumeId=volume_id)
        except Exception as exc:
            raise ProviderError(f"failed to delete volume {volume_id}: {exc}") from exc
        return RollbackRecord(
            finding_id=finding.id,
            provider="aws",
            account=finding.account,
            resource_id=volume_id,
            action_type=finding.action_type,
            rollback_data={"snapshot_id": snap["SnapshotId"], "region": region, "availability_zone": az},
            rollback_note=(
                "Volume was snapshotted before deletion; rollback creates a NEW "
                "volume from that snapshot (its volume ID will differ from the original)."
            ),
        )

    def _rollback_delete_orphaned_volume(self, record: RollbackRecord) -> None:
        account = self._require_account(record.account)
        ec2 = self._session(account).client("ec2", region_name=record.rollback_data["region"])
        try:
            ec2.create_volume(
                SnapshotId=record.rollback_data["snapshot_id"],
                AvailabilityZone=record.rollback_data["availability_zone"],
            )
        except Exception as exc:
            raise ProviderError(f"failed to restore volume from snapshot: {exc}") from exc

    def _execute_delete_unused_eip(self, finding: "Finding") -> RollbackRecord:
        account = self._require_account(finding.account)
        region = finding.current_state["region"]
        ec2 = self._session(account).client("ec2", region_name=region)
        allocation_id = finding.current_state["allocation_id"]
        try:
            ec2.release_address(AllocationId=allocation_id)
        except Exception as exc:
            raise ProviderError(f"failed to release EIP {allocation_id}: {exc}") from exc
        return RollbackRecord(
            finding_id=finding.id,
            provider="aws",
            account=finding.account,
            resource_id=allocation_id,
            action_type=finding.action_type,
            rollback_data={"region": region},
            rollback_note=(
                "AWS cannot restore a specific released Elastic IP. Rollback "
                "allocates a NEW Elastic IP — update any DNS/config pointing "
                "at the old address."
            ),
        )

    def _rollback_delete_unused_eip(self, record: RollbackRecord) -> None:
        account = self._require_account(record.account)
        ec2 = self._session(account).client("ec2", region_name=record.rollback_data["region"])
        try:
            ec2.allocate_address(Domain="vpc")
        except Exception as exc:
            raise ProviderError(f"failed to allocate replacement EIP: {exc}") from exc

    def _execute_stop_idle_instance(self, finding: "Finding") -> RollbackRecord:
        account = self._require_account(finding.account)
        region = finding.current_state["region"]
        ec2 = self._session(account).client("ec2", region_name=region)
        instance_id = finding.current_state["instance_id"]
        try:
            ec2.stop_instances(InstanceIds=[instance_id])
        except Exception as exc:
            raise ProviderError(f"failed to stop instance {instance_id}: {exc}") from exc
        return RollbackRecord(
            finding_id=finding.id,
            provider="aws",
            account=finding.account,
            resource_id=instance_id,
            action_type=finding.action_type,
            rollback_data={"region": region, "instance_id": instance_id},
            rollback_note="Rollback starts the instance back up.",
        )

    def _rollback_stop_idle_instance(self, record: RollbackRecord) -> None:
        account = self._require_account(record.account)
        ec2 = self._session(account).client("ec2", region_name=record.rollback_data["region"])
        try:
            ec2.start_instances(InstanceIds=[record.rollback_data["instance_id"]])
        except Exception as exc:
            raise ProviderError(f"failed to start instance: {exc}") from exc

    def _execute_downsize_instance(self, finding: "Finding") -> RollbackRecord:
        account = self._require_account(finding.account)
        region = finding.current_state["region"]
        ec2 = self._session(account).client("ec2", region_name=region)
        instance_id = finding.current_state["instance_id"]
        previous_type = finding.current_state["previous_instance_type"]
        target_type = EC2_DOWNSIZE_MAP.get(previous_type)
        if target_type is None:
            raise ProviderError(f"no known smaller tier for instance type {previous_type!r}")
        try:
            ec2.stop_instances(InstanceIds=[instance_id])
            ec2.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])
            ec2.modify_instance_attribute(InstanceId=instance_id, InstanceType={"Value": target_type})
            ec2.start_instances(InstanceIds=[instance_id])
        except Exception as exc:
            raise ProviderError(f"failed to downsize instance {instance_id}: {exc}") from exc
        return RollbackRecord(
            finding_id=finding.id,
            provider="aws",
            account=finding.account,
            resource_id=instance_id,
            action_type=finding.action_type,
            rollback_data={"region": region, "instance_id": instance_id, "previous_instance_type": previous_type},
            rollback_note="Rollback stops the instance, restores its previous instance type, and starts it again.",
        )

    def _rollback_downsize_instance(self, record: RollbackRecord) -> None:
        account = self._require_account(record.account)
        ec2 = self._session(account).client("ec2", region_name=record.rollback_data["region"])
        instance_id = record.rollback_data["instance_id"]
        previous_type = record.rollback_data["previous_instance_type"]
        try:
            ec2.stop_instances(InstanceIds=[instance_id])
            ec2.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])
            ec2.modify_instance_attribute(InstanceId=instance_id, InstanceType={"Value": previous_type})
            ec2.start_instances(InstanceIds=[instance_id])
        except Exception as exc:
            raise ProviderError(f"failed to roll back instance size: {exc}") from exc

    def _execute_resize_database(self, finding: "Finding") -> RollbackRecord:
        account = self._require_account(finding.account)
        region = finding.current_state["region"]
        rds = self._session(account).client("rds", region_name=region)
        db_id = finding.current_state["db_instance_id"]
        previous_class = finding.current_state["previous_instance_class"]
        target_class = RDS_DOWNSIZE_MAP.get(previous_class)
        if target_class is None:
            raise ProviderError(f"no known smaller tier for db instance class {previous_class!r}")
        try:
            rds.modify_db_instance(DBInstanceIdentifier=db_id, DBInstanceClass=target_class, ApplyImmediately=True)
        except Exception as exc:
            raise ProviderError(f"failed to resize db instance {db_id}: {exc}") from exc
        return RollbackRecord(
            finding_id=finding.id,
            provider="aws",
            account=finding.account,
            resource_id=db_id,
            action_type=finding.action_type,
            rollback_data={"region": region, "db_instance_id": db_id, "previous_instance_class": previous_class},
            rollback_note=(
                "Rollback resizes the RDS instance back to its previous class "
                "(applied immediately — may cause a brief failover)."
            ),
        )

    def _rollback_resize_database(self, record: RollbackRecord) -> None:
        account = self._require_account(record.account)
        rds = self._session(account).client("rds", region_name=record.rollback_data["region"])
        try:
            rds.modify_db_instance(
                DBInstanceIdentifier=record.rollback_data["db_instance_id"],
                DBInstanceClass=record.rollback_data["previous_instance_class"],
                ApplyImmediately=True,
            )
        except Exception as exc:
            raise ProviderError(f"failed to roll back db instance size: {exc}") from exc

    # switch_to_spot / migrate_region: intentionally not implemented in this
    # pass (TODO). Both are HIGH-complexity, cross-cutting operations —
    # switching to spot needs full launch-config capture/replay, and region
    # migration needs a workload-specific plan. They're still correctly
    # classified as MEDIUM/HIGH risk in risk_classifier.py so they're never
    # silently skipped — they'll always route to approval, and this
    # provider raises NotImplementedError (via execute_action's getattr
    # dispatch) instead of a fake success if one is ever approved.

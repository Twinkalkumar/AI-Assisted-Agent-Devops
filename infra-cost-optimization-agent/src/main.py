"""CostGuard CLI — analyze / plan / apply / rollback / report.

    python src/main.py plan      # always dry-run: shows what WOULD happen
    python src/main.py apply     # executes LOW-risk findings + approved MEDIUM/HIGH ones
    python src/main.py apply --interactive   # also prompts on the CLI for pending approvals
    python src/main.py rollback <finding_id>
    python src/main.py report
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

import analyzer
import approval
import audit_log
import executor
from recommender import Finding, recommend
from risk_classifier import ClassifiedFinding, RiskLevel, classify_all

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
audit_log.configure_logging()
logger = logging.getLogger("costguard.main")

STATE_DIR = PROJECT_ROOT / "state"
PLAN_PATH = STATE_DIR / "plan_latest.json"


def _finding_to_dict(f: Finding) -> dict:
    return dataclasses.asdict(f)


def _finding_from_dict(d: dict) -> Finding:
    return Finding(**d)


def _classified_to_dict(c: ClassifiedFinding) -> dict:
    return {
        "finding": _finding_to_dict(c.finding),
        "risk": c.risk.value,
        "reasons": c.reasons,
        "auto_executable": c.auto_executable,
    }


def _classified_from_dict(d: dict) -> ClassifiedFinding:
    return ClassifiedFinding(
        finding=_finding_from_dict(d["finding"]),
        risk=RiskLevel(d["risk"]),
        reasons=d["reasons"],
        auto_executable=d["auto_executable"],
    )


def _load_plan() -> list[ClassifiedFinding]:
    if not PLAN_PATH.exists():
        raise SystemExit("No plan found — run `python src/main.py plan` first.")
    with PLAN_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return [_classified_from_dict(d) for d in raw["classified_findings"]]


def _save_plan(classified_findings: list[ClassifiedFinding], skipped: list) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classified_findings": [_classified_to_dict(c) for c in classified_findings],
        "skipped_resources": [{"resource_id": s.resource_id, "reason": s.reason} for s in skipped],
    }
    # Overwritten (not appended) each run — this is what keeps repeated
    # `plan` calls idempotent instead of accumulating duplicate findings.
    with PLAN_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _print_finding_line(c: ClassifiedFinding) -> None:
    f = c.finding
    auto = "auto" if c.auto_executable else "needs approval"
    print(
        f"  [{c.risk.value:6}] ({auto:14}) {f.provider}/{f.account} {f.resource_id} "
        f"— {f.action_type} — est. ${f.estimated_monthly_savings_usd:.2f}/mo"
    )
    print(f"           {f.description}")


def cmd_analyze(_args: argparse.Namespace) -> None:
    metrics, *_ = analyzer.analyze()
    print(f"Collected utilization data for {len(metrics)} resources:")
    by_type: dict[str, int] = {}
    for m in metrics:
        by_type[m.resource_type] = by_type.get(m.resource_type, 0) + 1
    for rtype, count in sorted(by_type.items()):
        print(f"  {rtype}: {count}")


def cmd_plan(_args: argparse.Namespace) -> None:
    metrics, thresholds, tag_policy, _providers, _providers_cfg = analyzer.analyze()
    findings, skipped = recommend(metrics, thresholds, tag_policy)
    classified = classify_all(findings, tag_policy)
    _save_plan(classified, skipped)

    print(f"\nPlan ({len(classified)} findings, {len(skipped)} resources skipped):\n")
    for c in sorted(classified, key=lambda c: c.risk.value):
        _print_finding_line(c)

    webhook_url = os.environ.get("APPROVAL_WEBHOOK_URL")
    store = approval.ApprovalStore()
    for c in classified:
        if c.auto_executable:
            continue
        approval.register_file_approval_request(c, store)
        if webhook_url:
            approval.send_webhook_approval_request(c, store, webhook_url)

    if skipped:
        print(f"\nSkipped (dead-man's switch / insufficient data):")
        for s in skipped:
            print(f"  {s.resource_id}: {s.reason}")

    total_savings = sum(c.finding.estimated_monthly_savings_usd for c in classified)
    auto_savings = sum(c.finding.estimated_monthly_savings_usd for c in classified if c.auto_executable)
    print(f"\nTotal potential savings: ${total_savings:.2f}/mo (${auto_savings:.2f}/mo auto-executable)")
    print("Nothing has been executed. Run `python src/main.py apply` to act on this plan.")


def cmd_apply(args: argparse.Namespace) -> None:
    classified = _load_plan()
    thresholds = analyzer.load_yaml("thresholds.yaml")
    providers_cfg = analyzer.load_yaml("providers.yaml")
    providers = analyzer.build_providers(providers_cfg)
    store = approval.ApprovalStore()

    if args.interactive:
        for c in classified:
            if c.auto_executable:
                continue
            existing = store.get(c.finding.id)
            if existing is not None and existing.status != "pending":
                continue
            approval.request_cli_approval(c, store)

    max_auto = thresholds.get("max_auto_actions_per_run", 10)
    executed_low = executor.apply_low_risk(classified, providers, max_auto)
    executed_approved = executor.apply_approved(classified, providers, store)

    print(f"Executed {len(executed_low)} LOW-risk finding(s) automatically:")
    for fid in executed_low:
        print(f"  {fid}")
    print(f"Executed {len(executed_approved)} previously-approved finding(s):")
    for fid in executed_approved:
        print(f"  {fid}")

    pending = [
        c for c in classified
        if not c.auto_executable and c.finding.id not in executed_approved
        and (store.get(c.finding.id) is None or store.get(c.finding.id).status == "pending")
    ]
    if pending:
        print(f"\n{len(pending)} finding(s) still awaiting approval — see state/approvals.json,")
        print("or re-run with --interactive to decide them on the CLI now.")


def cmd_rollback(args: argparse.Namespace) -> None:
    providers_cfg = analyzer.load_yaml("providers.yaml")
    providers = analyzer.build_providers(providers_cfg)
    executor.rollback(args.finding_id, providers)
    print(f"Rolled back {args.finding_id}")


def cmd_report(_args: argparse.Namespace) -> None:
    entries = audit_log.read_audit_log()
    executed_ids = {e["finding_id"] for e in entries if e["event_type"] == "executed"}
    rolled_back_ids = {e["finding_id"] for e in entries if e["event_type"] == "rolled_back"}
    failed_ids = {e["finding_id"] for e in entries if e["event_type"] == "execution_failed"}
    realized_ids = executed_ids - rolled_back_ids

    savings_realized = 0.0
    savings_pending = 0.0
    per_provider: dict[str, float] = {}

    if PLAN_PATH.exists():
        classified = _load_plan()
        by_id = {c.finding.id: c for c in classified}
        for fid in realized_ids:
            c = by_id.get(fid)
            if c is None:
                continue
            savings_realized += c.finding.estimated_monthly_savings_usd
            per_provider[c.finding.provider] = per_provider.get(c.finding.provider, 0.0) + c.finding.estimated_monthly_savings_usd
        for c in classified:
            if not c.auto_executable and c.finding.id not in executed_ids:
                savings_pending += c.finding.estimated_monthly_savings_usd

    print("CostGuard report")
    print("=================")
    print(f"Savings realized:          ${savings_realized:.2f}/mo")
    print(f"Savings pending approval:  ${savings_pending:.2f}/mo")
    print(f"Actions executed:          {len(executed_ids)}")
    print(f"Actions rolled back:       {len(rolled_back_ids)}")
    print(f"Actions failed:            {len(failed_ids)}")
    if per_provider:
        print("\nRealized savings per provider:")
        for provider, amount in sorted(per_provider.items()):
            print(f"  {provider}: ${amount:.2f}/mo")


def main() -> None:
    parser = argparse.ArgumentParser(prog="costguard")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("analyze", help="Collect utilization data and print a summary.").set_defaults(func=cmd_analyze)

    sub.add_parser("plan", help="Show findings and risk classification. Never executes anything.").set_defaults(
        func=cmd_plan
    )

    apply_parser = sub.add_parser("apply", help="Execute the latest plan (LOW-risk auto + approved).")
    apply_parser.add_argument(
        "--interactive", action="store_true", help="Prompt on the CLI for any pending MEDIUM/HIGH approvals first."
    )
    apply_parser.set_defaults(func=cmd_apply)

    rollback_parser = sub.add_parser("rollback", help="Reverse a previously executed action.")
    rollback_parser.add_argument("finding_id")
    rollback_parser.set_defaults(func=cmd_rollback)

    sub.add_parser("report", help="Show savings realized/pending and action counts.").set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

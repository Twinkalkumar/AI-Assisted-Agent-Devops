"""CLI entrypoint for the Scalaten cost-optimization agent.

Usage:
    python src/main.py run "<task>" [--dry-run] [--cost-ceiling 0.05]
    python src/main.py report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from agent import ScalatenAgent
from cost_tracker import CostTracker
from router import Router


def cmd_run(args: argparse.Namespace) -> None:
    """Route (and, unless --dry-run, execute) a single task."""
    agent = ScalatenAgent()
    result = agent.run(
        task=args.task,
        cost_ceiling_usd=args.cost_ceiling,
        dry_run=args.dry_run,
    )

    print(f"complexity : {result.complexity}")
    print(f"chosen     : {result.provider}/{result.model}")
    print(f"reason     : {result.reason}")
    print(f"est. cost  : ${result.estimated_cost_usd:.6f}")

    if result.dry_run:
        print("\n[dry-run] no API call was made.")
        return

    if result.attempts:
        for attempt in result.attempts:
            print(f"  fallback skipped -> {attempt}")

    if result.text is None:
        print("\nAll providers failed; no response generated.")
        sys.exit(1)

    print(f"actual cost: ${result.actual_cost_usd:.6f}")
    print(f"latency    : {result.latency_ms:.0f}ms")
    print("\n--- response ---")
    print(result.text)


def cmd_report(args: argparse.Namespace) -> None:
    """Print total spend, per-provider breakdown, and savings vs baseline."""
    tracker = CostTracker()
    router = Router()
    summary = tracker.summary(baseline_model=router.most_expensive())

    print("=== Scalaten spend report ===")
    print(f"total calls : {summary['total_calls']}")
    print(f"total spend : ${summary['total_cost_usd']:.6f}")

    print("\nby provider:")
    for provider, stats in summary["by_provider"].items():
        print(
            f"  {provider:10s} calls={stats['calls']:<4d} "
            f"cost=${stats['cost_usd']:.6f} "
            f"tokens(in/out)={stats['input_tokens']}/{stats['output_tokens']}"
        )

    if "baseline_cost_usd" in summary:
        print(
            f"\nbaseline ({summary['baseline_model']}, always used): "
            f"${summary['baseline_cost_usd']:.6f}"
        )
        print(
            f"savings vs baseline: ${summary['savings_usd']:.6f} "
            f"({summary['savings_pct']:.1f}%)"
        )
    else:
        print("\nNo calls logged yet — run a task first to see savings.")


def build_parser() -> argparse.ArgumentParser:
    """Construct the `run` / `report` subcommand parser."""
    parser = argparse.ArgumentParser(
        prog="scalaten", description="Multi-provider LLM cost-optimization agent"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Route and (optionally) execute a task")
    run_parser.add_argument("task", help="The task/prompt to route")
    run_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show the routing decision and estimated cost without calling the provider",
    )
    run_parser.add_argument(
        "--cost-ceiling", type=float, default=None,
        help="Max estimated $ for this request (overrides config default)",
    )
    run_parser.set_defaults(func=cmd_run)

    report_parser = subparsers.add_parser(
        "report", help="Print total spend, per-provider breakdown, and savings"
    )
    report_parser.set_defaults(func=cmd_report)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

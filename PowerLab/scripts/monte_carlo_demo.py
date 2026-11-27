"""Monte Carlo 演示（真实执行，小样本）。"""

from __future__ import annotations

import argparse
import json

from experiments import BudgetCounter
from experiments.monte_carlo_experiment import run_monte_carlo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Monte Carlo samples with real SPICE")
    parser.add_argument("--profile", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-runs", type=int, default=8)
    args = parser.parse_args(argv)
    result = run_monte_carlo(
        profile=args.profile,
        budget=BudgetCounter(max_spice_runs=args.max_runs),
        resume=args.resume,
    )
    print(
        json.dumps(
            {
                "profile": result["profile"],
                "records": len(result["records"]),
                "states": result["statistics"].get("completed_count"),
                "pass_ratio": result["pass_ratio"]["all_samples"]["wilson"],
                "spice_runs": result["budget"]["spice_runs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

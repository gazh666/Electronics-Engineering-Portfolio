"""理论 / SPICE 对照演示。"""

from __future__ import annotations

import argparse
import json

from experiments import BudgetCounter
from experiments.theoretical_comparison import run_theoretical_comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run theory vs SPICE comparison")
    parser.add_argument("--profile", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--max-runs", type=int, default=30)
    args = parser.parse_args(argv)
    result = run_theoretical_comparison(
        budget=BudgetCounter(max_spice_runs=args.max_runs), profile=args.profile
    )
    print(
        json.dumps(
            {
                "cases": result["case_count"],
                "theory_checks": result["summary"]["theory_checks"],
                "model_checks": result["summary"]["model_checks"],
                "spice_runs": result["budget"]["spice_runs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

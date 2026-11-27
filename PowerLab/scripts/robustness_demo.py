"""闭环容差与设计鲁棒性演示。"""

from __future__ import annotations

import argparse
import json

from experiments import BudgetCounter
from experiments.robustness_comparison import run_robustness_comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Closed-loop tolerance and design robustness")
    parser.add_argument("--case", default="VAL001")
    parser.add_argument("--profile", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--max-runs", type=int, default=4)
    args = parser.parse_args(argv)
    result = run_robustness_comparison(
        case_id=args.case,
        budget=BudgetCounter(max_spice_runs=args.max_runs),
        profile=args.profile,
    )
    print(
        json.dumps(
            {
                "screen": result["closed_loop_screen_summary"],
                "design_b": result["designs"]["design_b"],
                "spice_runs": len(result["closed_loop_spice_runs"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

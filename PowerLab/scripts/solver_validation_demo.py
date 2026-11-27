"""求解器参数对照演示。"""

from __future__ import annotations

import argparse
import json

from experiments import BudgetCounter
from experiments.solver_comparison import run_solver_comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare ngspice solver settings")
    parser.add_argument("--case", default="VAL001")
    parser.add_argument("--profile", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--max-runs", type=int, default=10)
    args = parser.parse_args(argv)
    variants = ("method_gear",) if args.profile == "smoke" else None
    result = run_solver_comparison(
        case_id=args.case,
        budget=BudgetCounter(max_spice_runs=args.max_runs),
        profile=args.profile,
        variant_labels=variants,
    )
    print(json.dumps({"summary": result["summary"], "runs": len(result["runs"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

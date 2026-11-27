"""角点分析演示。"""

from __future__ import annotations

import argparse
import json

from experiments import BudgetCounter
from experiments.corner_experiment import run_corner_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run explicit corner analysis")
    parser.add_argument("--case", default="VAL001")
    parser.add_argument("--max-runs", type=int, default=12)
    args = parser.parse_args(argv)
    result = run_corner_experiment(
        case_id=args.case, budget=BudgetCounter(max_spice_runs=args.max_runs)
    )
    print(json.dumps({"summary": result["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

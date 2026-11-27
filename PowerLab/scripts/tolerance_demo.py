"""单参数容差演示。"""

from __future__ import annotations

import argparse
import json

from experiments import BudgetCounter
from experiments.tolerance_experiment import run_tolerance_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one-factor tolerance study")
    parser.add_argument("--case", default="VAL001")
    parser.add_argument("--max-runs", type=int, default=20)
    args = parser.parse_args(argv)
    result = run_tolerance_experiment(
        case_id=args.case, budget=BudgetCounter(max_spice_runs=args.max_runs)
    )
    print(
        json.dumps(
            {
                "parameters": len(result.get("tolerances", {})),
                "spice_runs": result["budget"]["spice_runs"],
                "dominant": {
                    metric: payload.get("dominant_parameter")
                    for metric, payload in result.get("first_order_propagation", {})
                    .get("metrics", {})
                    .items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""时间步长收敛演示。"""

from __future__ import annotations

import argparse
import json

from experiments import BudgetCounter
from experiments.timestep_convergence import run_timestep_convergence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run timestep convergence study")
    parser.add_argument("--case", default="VAL001")
    parser.add_argument("--profile", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--max-runs", type=int, default=10)
    args = parser.parse_args(argv)
    steps = (200e-9, 100e-9, 50e-9) if args.profile == "smoke" else None
    result = run_timestep_convergence(
        case_id=args.case,
        budget=BudgetCounter(max_spice_runs=args.max_runs),
        profile=args.profile,
        maximum_steps_s=steps,
    )
    print(
        json.dumps(
            {
                "status": result.get("analysis", {}).get("overall_status", result.get("status")),
                "metrics": result.get("analysis", {}).get("metrics", []),
                "orders": result.get("convergence_orders", {}),
                "spice_runs": result["budget"]["spice_runs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

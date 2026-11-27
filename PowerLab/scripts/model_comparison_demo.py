"""多层模型对照演示（A/B/C/D）。"""

from __future__ import annotations

import argparse
import json

from experiments import BudgetCounter
from experiments.theoretical_comparison import run_theoretical_comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare ideal/averaged/switch/MOSFET models")
    parser.add_argument("--profile", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--max-runs", type=int, default=30)
    args = parser.parse_args(argv)
    result = run_theoretical_comparison(
        budget=BudgetCounter(max_spice_runs=args.max_runs), profile=args.profile
    )
    rows = [
        {
            "case": row["case_id"],
            "level": row["model_level"],
            "vout": row.get("output_voltage_mean_v"),
            "ripple": row.get("inductor_current_ripple_a"),
            "efficiency": row.get("efficiency_system_percent"),
        }
        for row in result["model_matrix"]
    ]
    print(json.dumps({"matrix": rows, "checks": result["summary"]["model_checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

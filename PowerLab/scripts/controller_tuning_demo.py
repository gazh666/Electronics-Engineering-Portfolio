"""控制器整定演示：3×3 PI 矩阵 + 可选真实 SPICE 复核。"""

from __future__ import annotations

import argparse

import pandas as pd

from experiments.controller_tuning import run_controller_tuning_experiment

from .stage7_common import save_csv, save_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stage 7 controller tuning demo")
    parser.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
    args = parser.parse_args(argv)

    report = run_controller_tuning_experiment(save=True)
    matrix = pd.DataFrame(report["matrix"])
    if not matrix.empty:
        save_csv("controller_tuning_matrix.csv", matrix)
    save_json("controller_tuning_demo.json", report)
    print(
        f"[tuning] pwm_gain={report['pwm_gain']:.4f} "
        f"selected kp={report['selected_by_score']['kp']:.5f} "
        f"ki={report['selected_by_score']['ki']:.4f} "
        f"PM={report['selected_by_score']['phase_margin_deg']:.2f} deg "
        f"class={report['selected_by_score']['classification']}"
    )
    for row in matrix.to_dict(orient="records"):
        print(
            f"  kp_x{row['kp_factor']} ki_x{row['ki_factor']} "
            f"PM={row['phase_margin_deg']:.2f} GM={row['gain_margin_db']} "
            f"class={row['classification']} score={row['score']:.3f}"
        )
    for record in report["spice_checks"]:
        print(
            f"  spice[{record['label']}] run={record['run_id']} "
            f"max_dev={record['event_metrics'].get('maximum_absolute_deviation_v')} V "
            f"overshoot={record['startup'].get('overshoot_percent')}%"
        )
    print("saved:", "results/stage7/demos/controller_tuning_demo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

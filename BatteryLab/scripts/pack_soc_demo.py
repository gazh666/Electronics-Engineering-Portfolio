"""3S 单体 SOC 与均衡电流补偿演示（Task 29 / Task 30 / Task 40）。"""

from __future__ import annotations

import numpy as np

from experiments.pack_estimation_experiment import run_pack_estimation_experiment
from scripts.stage7_common import (
    finish,
    open_run,
    plot_categories,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)


def main() -> None:
    run = open_run("stage7")
    result = run_pack_estimation_experiment()
    time_axis = np.linspace(0.0, result["balance_duration_s"] + result["rest_duration_s"], 5)
    cell_labels = [f"cell{index + 1}" for index in range(len(result["initial_socs"]))]

    write_metadata(
        run,
        script="pack_soc_demo",
        description="3S 电池组逐节 SOC 估计与 40 mA 被动均衡电流补偿（合成真值）",
        extra={
            "source_type": "synthetic_truth",
            "balancing_current_note": result["balancing_current_note"],
        },
    )
    rows = []
    for case in result["cases"]:
        for index, label in enumerate(cell_labels):
            rows.append(
                {
                    "case": case["case"],
                    "cell": label,
                    "truth_soc": case["truth_soc"][index],
                    "estimated_soc": case["estimated_soc"][index],
                    "error_pp": case["cell_error_pp"][index],
                    "max_absolute_error_pp": case["max_absolute_error_pp"],
                    "soc_spread_pp": case["soc_spread_pp"],
                }
            )
    write_rows(
        run,
        "pack_soc_summary.csv",
        rows,
        header=["case", "cell", "truth_soc", "estimated_soc", "error_pp", "max_absolute_error_pp", "soc_spread_pp"],
    )
    write_payload(run, "pack_soc_experiment.json", result)

    initial = result["initial_socs"]
    truth_final = result["cases"][0]["truth_soc"]
    estimate_b = result["cases"][1]["estimated_soc"]
    plot_categories(
        run,
        "20_pack_cell_soc.png",
        cell_labels,
        {
            "initial SOC": initial,
            "final truth SOC": truth_final,
            "final estimate (balancing included)": estimate_b,
        },
        title=f"3S per-cell SOC — synthetic truth (run {run.run_id})",
        ylabel="SOC (0-1)",
    )
    plot_categories(
        run,
        "21_balancing_comparison.png",
        cell_labels,
        {
            "ignore balancing": result["cases"][0]["cell_error_pp"],
            "include balancing": result["cases"][1]["cell_error_pp"],
            "balancing estimate +20% error": result["cases"][2]["cell_error_pp"],
        },
        title=f"Per-cell SOC error with/without balancing (run {run.run_id})",
        ylabel="final SOC error (percentage point)",
        horizontal=0.0,
    )
    finish(run, "pack soc demo done")
    print(
        f"[pack_soc_demo] run={run.run_id} balance_current={result['estimated_balancing_current_a']*1000:.2f} mA "
        f"charge={result['balancing_charge_consumed_ah']*1000:.2f} mAh"
    )
    for case in result["cases"]:
        print(
            f"  {case['case']}: max_error={case['max_absolute_error_pp']:.4f} pp "
            f"mean={case['mean_absolute_error_pp']:.4f} pp spread={case['soc_spread_pp']:.3f} pp"
        )
    print(f"  improvement (A->B) = {result['compensation_improvement_pp']:.4f} pp")


if __name__ == "__main__":
    main()

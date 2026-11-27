"""四种 SOC 算法公平对照演示（Task 15 / Task 40）。"""

from __future__ import annotations

import numpy as np

from experiments.common import measurement_bundle
from experiments.soc_comparison import METHODS, comparison_table, run_soc_comparison
from scripts.stage7_common import (
    finish,
    open_run,
    plot_histogram,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)

DATASETS = ("us06_50", "us06_80", "bjdst_50", "bjdst_80")
PLOT_DATASET = "us06_50"


def main() -> None:
    run = open_run("stage7")
    results = run_soc_comparison(DATASETS)
    table = comparison_table(results)

    write_metadata(
        run,
        script="soc_comparison_demo",
        description="四种 SOC 算法在相同窗口、相同初始 SOC、相同容量下的公平对照",
        extra={"datasets": list(DATASETS), "methods": list(METHODS)},
    )
    write_payload(run, "soc_method_comparison.json", results)
    write_rows(
        run,
        "soc_method_comparison.csv",
        table,
        header=[
            "dataset",
            "method",
            "mae_pp",
            "rmse_pp",
            "max_absolute_error_pp",
            "final_error_pp",
            "coverage_fraction",
            "valid_sample_count",
            "sample_count",
            "voltage_rmse_v",
            "status",
        ],
    )

    measurement = measurement_bundle(PLOT_DATASET)
    traces = {"reference SOC (experimental)": (measurement["time_s"], measurement["reference_soc"])}
    errors = {}
    for method in METHODS:
        payload = results["datasets"][PLOT_DATASET]["methods"][method]
        rows = payload["rows"]
        time_s = np.asarray([row["time_s"] for row in rows], dtype=float)
        estimated = np.asarray(
            [np.nan if row["estimated_soc"] is None else row["estimated_soc"] for row in rows], dtype=float
        )
        traces[method] = (time_s, estimated)
        errors[method] = (estimated - measurement["reference_soc"]) * 100.0

    plot_series(
        run,
        "11_four_method_comparison.png",
        traces,
        title=f"Four SOC methods — {PLOT_DATASET} (run {run.run_id})",
        xlabel="time (s)",
        ylabel="SOC (0-1)",
    )
    finite_errors = np.concatenate([values[np.isfinite(values)] for values in errors.values()])
    plot_histogram(
        run,
        "13_soc_error_distribution.png",
        finite_errors,
        title=f"Combined SOC error distribution — {PLOT_DATASET} (run {run.run_id})",
        xlabel="estimated - reference (percentage point)",
    )

    # 逐数据集写出估计 SOC（长表），便于后续核查。
    long_rows = []
    for dataset, entry in results["datasets"].items():
        for method, payload in entry["methods"].items():
            for row in payload["rows"]:
                long_rows.append(
                    {
                        "dataset": dataset,
                        "method": method,
                        "time_s": row["time_s"],
                        "estimated_soc": row["estimated_soc"],
                        "status": row["status"],
                    }
                )
    write_rows(
        run,
        "estimated_soc.csv",
        long_rows,
        header=["dataset", "method", "time_s", "estimated_soc", "status"],
    )
    finish(run, "soc comparison demo done")
    for row in table:
        print(
            f"[soc_comparison_demo] {row['dataset']:10s} {row['method']:20s} "
            f"MAE={row['mae_pp']:.3f} RMSE={row['rmse_pp']:.3f} max={row['max_absolute_error_pp']:.3f} "
            f"cov={row['coverage_fraction']:.4f}"
        )
    print(f"[soc_comparison_demo] run={run.run_id}")


if __name__ == "__main__":
    main()

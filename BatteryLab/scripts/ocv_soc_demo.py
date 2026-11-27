"""OCV-SOC 反向查表演示（Task 8 / Task 9 / Task 40）。"""

from __future__ import annotations

import numpy as np

from analysis.soc_metrics import calculate_soc_metrics
from estimation.estimation_runner import replay_raw_ocv, summarize_replay
from experiments.common import build_ocv_table, measurement_bundle, rows_metric_input
from scripts.stage7_common import (
    finish,
    open_run,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)

DATASET = "us06_50"


def main() -> None:
    run = open_run("soc_estimation")
    table = build_ocv_table()
    audit = table.audit()
    soc_grid = np.asarray(table.soc_table)
    ocv = np.asarray(table.ocv_table_v)
    midpoints, slopes = table.slope_series()
    low_observability = [
        {"soc": float(x), "slope_v_per_soc": float(s), "status": "LOW_OBSERVABILITY"}
        for x, s in zip(midpoints, slopes)
        if float(s) < 0.2
    ]

    measurement = measurement_bundle(DATASET)
    rows = replay_raw_ocv(measurement["samples"], table)
    ref, estimated, time_s = rows_metric_input(rows, measurement["reference_soc"])
    metrics = calculate_soc_metrics(ref, estimated, time_s)
    metrics.update(summarize_replay(rows))
    metrics.update(
        {
            "dataset": DATASET,
            "method": "raw_voltage_ocv",
            "monotonic_adjusted_count": audit["monotonic_adjusted_count"],
            "low_observability_intervals": len(low_observability),
            "note": "带载端电压直接当 OCV，包含欧姆与极化压降，物理上不等价于 OCV。",
        }
    )

    write_metadata(
        run,
        script="ocv_soc_demo",
        description="由真实 CALCE OCV 曲线构造单调反查表并在 US06 上做原始端电压查表",
        extra={"dataset": DATASET, "ocv_points": int(soc_grid.size)},
    )
    write_rows(
        run,
        "ocv_table.csv",
        [{"soc": float(s), "ocv_v": float(v)} for s, v in zip(soc_grid, ocv)],
    )
    write_rows(
        run,
        "ocv_slope.csv",
        [{"soc_mid": float(m), "slope_v_per_soc": float(s)} for m, s in zip(midpoints, slopes)],
    )
    write_payload(run, "ocv_audit.json", audit)
    write_payload(
        run,
        "raw_voltage_metrics.json",
        {**metrics, "low_observability_intervals": low_observability},
    )
    plot_series(
        run,
        "02_ocv_inverse_curve.png",
        {"OCV(SOC) monotonic envelope": (soc_grid, ocv)},
        title=f"OCV-SOC lookup table (run {run.run_id})",
        xlabel="SOC (0-1)",
        ylabel="OCV (V)",
    )
    plot_series(
        run,
        "03_ocv_slope.png",
        {"dOCV/dSOC": (midpoints, slopes)},
        title=f"Local OCV slope (run {run.run_id})",
        xlabel="SOC (0-1)",
        ylabel="dOCV/dSOC (V per unit SOC)",
        horizontal=[(0.2, "minimum observable slope 0.2")],
    )
    plot_series(
        run,
        "04_ocv_platform_uncertainty.png",
        {"SOC estimate from measured terminal voltage": (time_s, estimated)},
        title=f"Raw terminal-voltage OCV lookup — {DATASET} (run {run.run_id})",
        xlabel="time (s)",
        ylabel="SOC (0-1)",
    )
    finish(run, f"ocv demo done: raw OCV RMSE={metrics['rmse_pp']:.3f} pp")
    print(
        f"[ocv_soc_demo] run={run.run_id} points={soc_grid.size} "
        f"monotonic_adjusted={audit['monotonic_adjusted_count']} "
        f"raw_OCV_RMSE={metrics['rmse_pp']:.3f} pp coverage={metrics['coverage_fraction']:.4f} "
        f"low_observability_intervals={len(low_observability)}"
    )


if __name__ == "__main__":
    main()

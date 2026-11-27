"""安时积分 SOC 演示（Task 6 / Task 40）。"""

from __future__ import annotations

import numpy as np

from analysis.soc_metrics import calculate_soc_metrics, soc_error_distribution
from estimation.coulomb_counter import CoulombCounter
from estimation.estimation_runner import replay_coulomb_counting, summarize_replay
from experiments.common import frozen_capacity_ah, measurement_bundle, rows_metric_input
from scripts.stage7_common import (
    finish,
    open_run,
    plot_histogram,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)

DATASET = "dst_50"


def main() -> None:
    run = open_run("soc_estimation")
    measurement = measurement_bundle(DATASET)
    counter = CoulombCounter(capacity_ah=frozen_capacity_ah(), soc=float(measurement["initial_soc"]))
    rows = replay_coulomb_counting(measurement["samples"], counter)
    ref, estimated, time_s = rows_metric_input(rows, measurement["reference_soc"])
    metrics = calculate_soc_metrics(ref, estimated, time_s)
    metrics.update(summarize_replay(rows))
    metrics.update(
        {
            "dataset": DATASET,
            "capacity_ah": frozen_capacity_ah(),
            "bound_event_count": len(counter.bound_events),
            "reference_source": "experimental_soc_reference",
            "note": "参考轨迹由同一电流与容量积分得到，零误差仅证明积分实现一致。",
        }
    )
    distribution = soc_error_distribution(ref, estimated)

    write_metadata(
        run,
        script="coulomb_counting_demo",
        description="安时积分在 CALCE DST 50%SOC 动态工况上的 SOC 估计",
        extra={"dataset": DATASET, "model_id": "calce_sp2_25c_inr18650_20r_first_order_v1"},
    )
    write_rows(
        run,
        "measurements.csv",
        [
            {"time_s": float(t), "current_a": float(i), "voltage_v": float(v)}
            for t, i, v in zip(measurement["time_s"], measurement["current_a"], measurement["voltage_v"])
        ],
    )
    write_rows(run, "reference_soc.csv", [{"time_s": float(t), "soc": float(s)} for t, s in zip(time_s, ref)])
    write_rows(
        run,
        "estimated_soc.csv",
        [
            {"time_s": row["time_s"], "estimated_soc": row["estimated_soc"], "status": row["status"]}
            for row in rows
        ],
    )
    write_payload(run, "estimation_metrics.json", metrics)
    write_payload(run, "soc_error_distribution.json", distribution)
    plot_series(
        run,
        "01_coulomb_soc_curve.png",
        {"reference SOC (experimental)": (time_s, ref), "coulomb counting": (time_s, estimated)},
        title=f"Ampere-hour integration SOC — {DATASET} (run {run.run_id})",
        xlabel="time (s)",
        ylabel="SOC (0-1)",
    )
    plot_histogram(
        run,
        "13_soc_error_distribution.png",
        (estimated - ref) * 100.0,
        title=f"SOC error distribution — {DATASET} (run {run.run_id})",
        xlabel="estimated - reference (percentage point)",
    )
    finish(run, f"coulomb demo done: RMSE={metrics['rmse_pp']:.4f} pp")
    print(
        f"[coulomb_counting_demo] run={run.run_id} dataset={DATASET} "
        f"RMSE={metrics['rmse_pp']:.4f} pp max={metrics['max_absolute_error_pp']:.4f} pp "
        f"coverage={metrics['coverage_fraction']:.4f}"
    )


if __name__ == "__main__":
    main()

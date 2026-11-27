"""ECM 端电压残差反馈观测器演示（Task 12 / Task 13 / Task 40）。"""

from __future__ import annotations

import numpy as np

from analysis.soc_metrics import calculate_soc_metrics, calculate_voltage_metrics
from estimation.coulomb_counter import CoulombCounter
from estimation.ecm_observer import ECMObserver
from estimation.estimation_runner import replay_observer, summarize_replay
from experiments.common import (
    build_ocv_table,
    frozen_capacity_ah,
    frozen_r0_ohm,
    load_observer_config,
    measurement_bundle,
    observer_branches,
    rows_metric_input,
)
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
    measurement = measurement_bundle(DATASET)
    config = load_observer_config()["observer"]
    observer = ECMObserver(
        counter=CoulombCounter(capacity_ah=frozen_capacity_ah(), soc=float(measurement["initial_soc"])),
        r0_ohm=frozen_r0_ohm(),
        branches=observer_branches(),
        ocv_model=build_ocv_table(),
        correction_time_constant_s=float(config["correction_time_constant_s"]),
        minimum_ocv_slope=float(config["minimum_ocv_slope_v_per_soc"]),
        maximum_correction_rate=float(config["maximum_correction_rate_soc_per_s"]),
        maximum_residual_v=float(config["maximum_residual_v"]),
        current_step_threshold_a=float(config["current_step_threshold_a"]),
    )
    rows = replay_observer(observer, measurement["samples"])
    ref, estimated, time_s = rows_metric_input(rows, measurement["reference_soc"])
    metrics = calculate_soc_metrics(ref, estimated, time_s)
    metrics.update(summarize_replay(rows))
    predicted = [row.get("predicted_voltage_v") for row in rows]
    voltage_metrics = calculate_voltage_metrics(measurement["voltage_v"], predicted)
    residuals = [row.get("voltage_residual_v") for row in rows]
    metrics.update(
        {
            "dataset": DATASET,
            "method": "ecm_observer",
            "voltage_prediction": voltage_metrics,
            "saturation_event_count": len(observer.saturation_events),
            "observer_is_ekf": False,
            "note": "固定时间常数电压残差反馈，不是 EKF；不含协方差与卡尔曼增益。",
        }
    )

    write_metadata(
        run,
        script="ecm_observer_demo",
        description="一阶 RC ECM 端电压预测与残差反馈 SOC 校正",
        extra={"dataset": DATASET, "r0_ohm": frozen_r0_ohm()},
    )
    write_rows(
        run,
        "observer_states.csv",
        [
            {
                "time_s": row["time_s"],
                "estimated_soc": row["estimated_soc"],
                "predicted_soc": row["predicted_soc"],
                "predicted_voltage_v": row["predicted_voltage_v"],
                "voltage_residual_v": row["voltage_residual_v"],
                "correction": row["correction"],
                "status": row["status"],
            }
            for row in rows
        ],
    )
    write_payload(run, "observer_metrics.json", metrics)
    plot_series(
        run,
        "09_ecm_predicted_voltage.png",
        {
            "measured terminal voltage": (time_s, measurement["voltage_v"]),
            "ECM predicted voltage": (time_s, np.asarray([np.nan if v is None else v for v in predicted])),
        },
        title=f"ECM one-step voltage prediction — {DATASET} (run {run.run_id})",
        xlabel="time (s)",
        ylabel="voltage (V)",
    )
    plot_series(
        run,
        "10_ecm_residual.png",
        {"voltage residual (measured - predicted)": (time_s, np.asarray([np.nan if v is None else v for v in residuals]))},
        title=f"ECM voltage residual — {DATASET} (run {run.run_id})",
        xlabel="time (s)",
        ylabel="residual (V)",
        horizontal=[(0.0, "zero residual"), (0.35, "gate +0.35 V"), (-0.35, "gate -0.35 V")],
    )
    finish(run, "ecm observer demo done")
    print(
        f"[ecm_observer_demo] run={run.run_id} SOC_RMSE={metrics['rmse_pp']:.3f} pp "
        f"SOC_max={metrics['max_absolute_error_pp']:.3f} pp coverage={metrics['coverage_fraction']:.4f} "
        f"voltage_RMSE={voltage_metrics['rmse_v']:.5f} V residual_max={max(abs(v) for v in residuals if v is not None):.4f} V"
    )


if __name__ == "__main__":
    main()

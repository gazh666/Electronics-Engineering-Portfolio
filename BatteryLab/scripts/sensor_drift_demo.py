"""电流传感器误差与累计漂移演示（Task 18 / Task 19 / Task 40）。"""

from __future__ import annotations

from experiments.sensor_error_experiment import (
    run_calibration_comparison,
    run_offset_drift_fixture,
    run_sensor_error_experiment,
)
from scripts.stage7_common import (
    finish,
    open_run,
    plot_bar,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)

DATASET = "us06_50"


def main() -> None:
    run = open_run("soc_estimation")
    sensor = run_sensor_error_experiment(DATASET)
    drift = run_offset_drift_fixture()
    calibration = run_calibration_comparison(DATASET, injected_offset_ma=10.0)

    write_metadata(
        run,
        script="sensor_drift_demo",
        description="人工电流传感器扰动、长时间失调漂移教学夹具与零点校准对照",
        extra={
            "dataset": DATASET,
            "data_type": "public_data_with_synthetic_sensor_error",
            "seed": sensor["seed"],
        },
    )
    write_rows(
        run,
        "sensor_error_results.csv",
        sensor["rows"],
        header=[
            "scenario",
            "parameter",
            "unit",
            "mae_pp",
            "rmse_pp",
            "max_absolute_error_pp",
            "final_error_pp",
            "coverage_fraction",
            "theoretical_drift_pp",
            "bound_reached_count",
        ],
    )
    write_rows(
        run,
        "offset_drift_fixture.csv",
        drift,
        header=[
            "offset_ma",
            "duration_h",
            "capacity_ah",
            "simulated_drift_pp",
            "analytic_drift_pp",
            "step_s",
            "note",
        ],
    )
    write_payload(run, "calibration_comparison.json", calibration)
    write_payload(run, "sensor_error_metadata.json", {k: v for k, v in sensor.items() if k != "rows"})

    offsets = [row for row in sensor["rows"] if row["scenario"] == "offset"]
    plot_series(
        run,
        "05_offset_drift.png",
        {
            "24 h simulated (10 mA)": (
                [row["duration_h"] for row in drift if row["offset_ma"] == 10.0],
                [row["simulated_drift_pp"] for row in drift if row["offset_ma"] == 10.0],
            ),
            "24 h analytic (10 mA)": (
                [row["duration_h"] for row in drift if row["offset_ma"] == 10.0],
                [row["analytic_drift_pp"] for row in drift if row["offset_ma"] == 10.0],
            ),
            "24 h simulated (-10 mA)": (
                [row["duration_h"] for row in drift if row["offset_ma"] == -10.0],
                [row["simulated_drift_pp"] for row in drift if row["offset_ma"] == -10.0],
            ),
        },
        title=f"Current offset induced SOC drift (run {run.run_id})",
        xlabel="duration (h)",
        ylabel="SOC drift (percentage point)",
    )
    plot_bar(
        run,
        "06_calibration_before_after.png",
        [case["case"] for case in calibration["cases"]],
        [case["metrics"]["mae_pp"] for case in calibration["cases"]],
        title=f"Calibration comparison, injected offset 10 mA (run {run.run_id})",
        ylabel="SOC MAE (percentage point)",
    )
    plot_bar(
        run,
        "06b_offset_scan.png",
        [f"{row['parameter']:.0f} mA" for row in offsets],
        [row["final_error_pp"] for row in offsets],
        title=f"Final SOC error vs current offset — {DATASET} (run {run.run_id})",
        ylabel="final SOC error (percentage point)",
    )
    finish(run, "sensor drift demo done")
    print(f"[sensor_drift_demo] run={run.run_id} dataset={DATASET}")
    for row in offsets:
        print(
            f"  offset {row['parameter']:+.0f} mA -> final {row['final_error_pp']:+.3f} pp "
            f"MAE {row['mae_pp']:.3f} pp "
            f"(theory {row['theoretical_drift_pp']:+.3f} pp, bound {row['bound_reached_count']})"
        )
    for case in calibration["cases"]:
        print(f"  {case['case']}: MAE {case['metrics']['mae_pp']:.3f} pp")
    print(f"  calibration offset estimate: {calibration['calibration_offset_estimate_ma']:.3f} mA")


if __name__ == "__main__":
    main()

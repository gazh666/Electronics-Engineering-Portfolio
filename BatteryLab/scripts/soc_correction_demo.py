"""安时积分 + 静置 OCV 校正演示（Task 10 / Task 11 / Task 40）。

两部分证据：

1. 真实 CALCE 动态工况：DST/US06 连续动态段没有 ≥300 s 的充分静置，
   校正机会为 0 —— 这本身就是必须如实报告的结论。
2. 合成静置夹具（``synthetic_truth``）：用冻结 ECM 产生"放电 600 s + 静置
   1800 s"的端电压，初始 SOC 故意偏高 5 pp，验证静置检测、60 s 调度与校正
   收敛机制确实工作。
"""

from __future__ import annotations

import numpy as np

from analysis.soc_metrics import calculate_soc_metrics
from charging.battery_adapter import build_series_pack
from estimation.coulomb_counter import CoulombCounter
from estimation.estimation_runner import replay_rest_corrected, summarize_replay
from estimation.models import MeasurementSample
from experiments.common import (
    build_ocv_table,
    default_rest_detector,
    default_scheduler,
    frozen_capacity_ah,
    load_bundle,
    measurement_bundle,
    rows_metric_input,
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

DATASETS = ("dst_50", "us06_50")
FIXTURE_DISCHARGE_S = 600.0
FIXTURE_REST_S = 1800.0
FIXTURE_TRUTH_SOC = 0.55
FIXTURE_INITIAL_ESTIMATE = 0.50


def _synthetic_rest_fixture() -> tuple[list[MeasurementSample], np.ndarray, float]:
    bundle = load_bundle()
    pack = build_series_pack(bundle, [FIXTURE_TRUTH_SOC])
    capacity = frozen_capacity_ah()
    times = np.arange(0.0, FIXTURE_DISCHARGE_S + FIXTURE_REST_S + 1.0, 1.0)
    samples: list[MeasurementSample] = []
    discharged = 0.0
    for index, time_s in enumerate(times):
        current = 1.0 if time_s < FIXTURE_DISCHARGE_S else 0.0
        voltage = float(pack.pack_voltage(current))
        samples.append(
            MeasurementSample(
                time_s=float(time_s),
                current_a=float(current),
                terminal_voltage_v=voltage,
                temperature_c=25.0,
            )
        )
        if index == 0:
            reference = [FIXTURE_TRUTH_SOC]
        if index < times.size - 1:
            discharged += current * 1.0
            reference.append(FIXTURE_TRUTH_SOC - discharged / (3600.0 * capacity))
            pack.step(current, 1.0)
    return samples, np.asarray(reference, dtype=float), FIXTURE_INITIAL_ESTIMATE


def main() -> None:
    run = open_run("soc_estimation")
    table = build_ocv_table()
    real_rows = []
    all_events = []

    for dataset in DATASETS:
        measurement = measurement_bundle(dataset)
        counter = CoulombCounter(capacity_ah=frozen_capacity_ah(), soc=float(measurement["initial_soc"]))
        detector = default_rest_detector()
        scheduler = default_scheduler()
        rows = replay_rest_corrected(measurement["samples"], counter, table, detector, scheduler)
        ref, estimated, time_s = rows_metric_input(rows, measurement["reference_soc"])
        metrics = calculate_soc_metrics(ref, estimated, time_s)
        metrics.update(summarize_replay(rows))
        metrics.update(
            {
                "dataset": dataset,
                "correction_count": int(scheduler.correction_count),
                "rest_eligible_samples": int(sum(1 for row in rows if row.get("rest_eligible"))),
                "rest_detection_reason": detector.last_reason,
                "data_type": "public_experimental_data",
            }
        )
        real_rows.append(metrics)

    samples, reference, initial_estimate = _synthetic_rest_fixture()
    counter = CoulombCounter(capacity_ah=frozen_capacity_ah(), soc=initial_estimate)
    detector = default_rest_detector()
    scheduler = default_scheduler()
    fixture_rows = replay_rest_corrected(samples, counter, table, detector, scheduler)
    ref, estimated, time_s = rows_metric_input(fixture_rows, reference)
    fixture_metrics = calculate_soc_metrics(ref, estimated, time_s)
    fixture_metrics.update(summarize_replay(fixture_rows))
    fixture_metrics.update(
        {
            "dataset": "synthetic_rest_fixture",
            "initial_soc": initial_estimate,
            "initial_reference_soc": FIXTURE_TRUTH_SOC,
            "correction_count": int(scheduler.correction_count),
            "rest_eligible_samples": int(sum(1 for row in fixture_rows if row.get("rest_eligible"))),
            "data_type": "synthetic_truth",
        }
    )
    for event in scheduler.events:
        all_events.append({"dataset": "synthetic_rest_fixture", **event})

    write_metadata(
        run,
        script="soc_correction_demo",
        description="静置检测 + 调度式 OCV 校正；真实动态段无静置与合成静置夹具对照",
        extra={"real_datasets": list(DATASETS), "fixture": "synthetic_truth"},
    )
    write_payload(run, "correction_metrics.json", {"real": real_rows, "fixture": fixture_metrics})
    write_rows(
        run,
        "correction_events.csv",
        all_events,
        header=[
            "dataset",
            "time_s",
            "predicted_soc",
            "ocv_soc",
            "correction",
            "soc_after",
            "applied",
            "reason",
            "rest_duration_s",
            "voltage_slope_v_per_s",
        ],
    )
    write_rows(
        run,
        "fixture_soc.csv",
        [
            {"time_s": row["time_s"], "estimated_soc": row["estimated_soc"], "rest_eligible": row.get("rest_eligible")}
            for row in fixture_rows
        ],
        header=["time_s", "estimated_soc", "rest_eligible"],
    )

    rest_time = [row["time_s"] for row in fixture_rows]
    plot_series(
        run,
        "07_rest_detection_state.png",
        {
            "rest duration (s)": (rest_time, [row.get("rest_duration_s") or 0.0 for row in fixture_rows]),
            "rest eligible (0/1, scaled)": (rest_time, [3000.0 if row.get("rest_eligible") else 0.0 for row in fixture_rows]),
        },
        title=f"Rest detection — synthetic rest fixture (run {run.run_id})",
        xlabel="time (s)",
        ylabel="rest duration (s)",
        horizontal=[(300.0, "minimum rest 300 s")],
    )
    plot_series(
        run,
        "08_ocv_correction_events.png",
        {
            "reference SOC (synthetic truth)": (time_s, ref),
            "estimated before/after corrections": (time_s, estimated),
            "initial estimate 0.50": (time_s, np.full_like(time_s, FIXTURE_INITIAL_ESTIMATE)),
        },
        title=f"Rest OCV correction — synthetic fixture (run {run.run_id})",
        xlabel="time (s)",
        ylabel="SOC (0-1)",
    )
    plot_bar(
        run,
        "08b_correction_count.png",
        [row["dataset"] for row in real_rows] + ["synthetic_rest_fixture"],
        [row["correction_count"] for row in real_rows] + [fixture_metrics["correction_count"]],
        title=f"Applied OCV corrections (run {run.run_id})",
        ylabel="count",
    )
    finish(run, "soc correction demo done")
    for row in real_rows:
        print(
            f"[soc_correction_demo] {row['dataset']}: corrections={row['correction_count']} "
            f"rest_eligible={row['rest_eligible_samples']} reason={row['rest_detection_reason']}"
        )
    print(
        f"[soc_correction_demo] synthetic fixture: initial_error={ (initial_estimate - FIXTURE_TRUTH_SOC)*100:+.2f} pp "
        f"corrections={fixture_metrics['correction_count']} final_error={fixture_metrics['final_error_pp']:+.3f} pp "
        f"RMSE_before_correction_region={fixture_metrics['rmse_pp']:.3f} pp"
    )
    print(f"[soc_correction_demo] run={run.run_id}")


if __name__ == "__main__":
    main()

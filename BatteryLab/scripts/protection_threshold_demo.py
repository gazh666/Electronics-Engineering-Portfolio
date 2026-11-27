"""第五阶段实验 2：保护比较器阈值、迟滞与确认延时（真实 ngspice + 行为模型）。

运行：conda run -n kaifa_battery python -m scripts.protection_threshold_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from circuits.protection_comparator import (
    load_comparator_settings,
    run_overvoltage_comparator_spice,
)
from circuits.spice_utils import get_solve_count, reset_solve_counter
from protection.comparator import (
    ComparatorConfig,
    HysteresisComparator,
    chatter_count,
    evaluate_comparator,
)
from scripts.stage5_common import (
    check_at_least,
    check_at_most,
    check_within,
    stage5_limits,
    summarize_checks,
)
from storage.result_store import RunDirectory, write_json
from visualization.plots import plot_xy


def _noise_sequence(
    *,
    baseline_v: float,
    noise_rms_v: float,
    duration_s: float,
    step_s: float,
    seed: int = 42,
    settle_at_s: float = 0.2,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    times = np.arange(0.0, duration_s, step_s)
    values = np.full(times.size, baseline_v)
    values[times < settle_at_s] = baseline_v - 0.02
    values += rng.normal(0.0, noise_rms_v, times.size)
    return times, values


def run(root: Path | None = None) -> dict:
    reset_solve_counter()
    limits = stage5_limits()
    settings = load_comparator_settings()
    run_dir = RunDirectory("protection", root=root)
    run_dir.write_metadata(
        {
            "stage": "stage5",
            "experiment": "comparator_threshold_hysteresis_delay",
            "spice_backend": "ngspice via PySpice (voltage controlled switch with hysteresis)",
            "note": "SPICE 比较器为分立比较器教学等效；不是商业保护 IC 内部电路",
        }
    )

    spice = run_overvoltage_comparator_spice(settings)
    waveform = spice.waveform
    run_dir.write_waveform(
        ["time_s", "cell_voltage_v", "comparator_output_v"],
        [
            (time, cell, out)
            for time, cell, out in zip(
                waveform["time_s"].tolist(),
                waveform["cell_voltage_v"].tolist(),
                waveform["comparator_output_v"].tolist(),
            )
        ],
        name="comparator_sweep.csv",
    )
    run_dir.write_waveform(
        ["time_s", "cell_voltage_v", "filtered_voltage_v", "comparator_output_v"],
        [
            (time, cell, filtered, out)
            for time, cell, filtered, out in zip(
                waveform["step_time_s"].tolist(),
                waveform["step_cell_voltage_v"].tolist(),
                waveform["step_filtered_voltage_v"].tolist(),
                waveform["step_comparator_output_v"].tolist(),
            )
        ],
        name="comparator_step.csv",
    )
    (run_dir.path / "overvoltage_comparator.cir").write_text(spice.netlist, encoding="utf-8")
    plot_xy(
        waveform["time_s"],
        waveform["cell_voltage_v"],
        path=run_dir.path / "plots" / "comparator_sweep_input.png",
        xlabel="时间 / s",
        ylabel="单体电压 / V",
        title="比较器三角波扫描输入",
    )
    plot_xy(
        waveform["time_s"],
        waveform["comparator_output_v"],
        path=run_dir.path / "plots" / "comparator_sweep_output.png",
        xlabel="时间 / s",
        ylabel="比较器输出 / V",
        title="迟滞比较器输出（含回差）",
    )

    noise_times, noise_values = _noise_sequence(
        baseline_v=limits.cell_overvoltage_trip_v + 0.100,
        noise_rms_v=0.002,
        duration_s=3.0,
        step_s=0.001,
    )
    with_hysteresis = ComparatorConfig(
        name="OV_with_hysteresis",
        threshold=limits.cell_overvoltage_trip_v,
        hysteresis=limits.cell_overvoltage_trip_v - limits.cell_overvoltage_release_v,
        confirmation_delay_s=limits.overvoltage_delay_s,
        propagation_delay_s=limits.comparator_propagation_delay_s,
        direction="high",
    )
    without_hysteresis = ComparatorConfig(
        name="OV_without_hysteresis",
        threshold=limits.cell_overvoltage_trip_v,
        hysteresis=0.0,
        confirmation_delay_s=0.0,
        propagation_delay_s=0.0,
        direction="high",
    )
    readings_h = evaluate_comparator(with_hysteresis, noise_values.tolist(), noise_times.tolist())
    flips_h = chatter_count(readings_h)
    # 对照：同样的噪声，但信号均值正好压在阈值上，且无迟滞、无延时。
    edge_times, edge_values = _noise_sequence(
        baseline_v=limits.cell_overvoltage_trip_v,
        noise_rms_v=0.002,
        duration_s=3.0,
        step_s=0.001,
        settle_at_s=0.0,
    )
    readings_n = evaluate_comparator(without_hysteresis, edge_values.tolist(), edge_times.tolist())
    flips_n = chatter_count(readings_n)

    step_times = np.arange(0.0, 0.3, 0.0005)
    step_values = np.where(step_times < 0.05, 4.20, 4.30)
    delay_config = ComparatorConfig(
        name="OV_delay",
        threshold=limits.cell_overvoltage_trip_v,
        hysteresis=0.1,
        confirmation_delay_s=limits.overvoltage_delay_s,
        propagation_delay_s=limits.comparator_propagation_delay_s,
        direction="high",
    )
    delay_readings = evaluate_comparator(delay_config, step_values.tolist(), step_times.tolist())
    trip_time = next((item.trip_time_s for item in delay_readings if item.trip_time_s is not None), None)
    measured_delay = None if trip_time is None else trip_time - 0.05
    expected_delay = limits.overvoltage_delay_s + limits.comparator_propagation_delay_s

    verdicts = [
        check_within(
            "SPICE 跳闸电压误差",
            (spice.measured_trip_voltage_v or 0.0) - spice.cell_trip_voltage_v,
            0.005,
            "V",
        ),
        check_within(
            "SPICE 迟滞宽度误差",
            (spice.measured_hysteresis_v or 0.0) - spice.configured_hysteresis_v,
            0.010,
            "V",
        ),
        check_at_most(
            "SPICE RC 确认延时相对误差",
            spice.delay_relative_error if spice.delay_relative_error is not None else 1.0,
            0.10,
            "-",
        ),
        check_at_most("带迟滞抖动翻转次数", float(flips_h), 2.0, "次"),
        check_at_least("无迟滞对照抖动次数", float(flips_n), 10.0, "次"),
        check_at_most(
            "数字确认延时误差",
            abs((measured_delay or 0.0) - expected_delay),
            0.10 * expected_delay,
            "s",
        ),
    ]
    write_json(
        run_dir.path / "comparator_behavior.json",
        {
            "spice": spice.to_dict(),
            "chatter_with_hysteresis": flips_h,
            "chatter_without_hysteresis": flips_n,
            "digital_delay_measured_s": measured_delay,
            "digital_delay_expected_s": expected_delay,
        },
    )

    summary = {
        "run_id": run_dir.run_id,
        "real_spice_solves": get_solve_count(),
        "spice": spice.to_dict(),
        "noise": {
            "noise_rms_v": 0.002,
            "chatter_with_hysteresis": flips_h,
            "chatter_without_hysteresis": flips_n,
        },
        "digital_delay": {"measured_s": measured_delay, "expected_s": expected_delay},
        "verdict": summarize_checks(verdicts),
    }
    run_dir.write_summary(summary)
    run_dir.log(f"真实 SPICE 求解 {get_solve_count()} 次")
    run_dir.flush_log()
    return {"run_id": run_dir.run_id, "summary": summary, "checks": verdicts, "path": str(run_dir.path)}


def main() -> int:
    result = run()
    verdict = result["summary"]["verdict"]
    print(f"run_id={result['run_id']}")
    for check in verdict["checks"]:
        print(f"{check['status']:4s} {check['name']:30s} measured={check['measured']} limit={check['limit']}")
    print(f"total PASS={verdict['passed']} FAIL={verdict['failed']}")
    return 0 if verdict["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())




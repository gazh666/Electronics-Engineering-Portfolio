"""第六阶段实验 3：电流内环真实 SPICE（只闭合内环）。

验证内环跟踪、软启动与使能关断；不涉及电压外环，因此不能据此宣称 CC-CV 达标。

运行：conda run -n kaifa_battery python -m scripts.stage6_current_loop_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charging.config import load_charger_config, load_controller_config
from circuits.charger_buck import PackFixture, step_expression
from circuits.charger_current_feedback import CurrentLoopParameters, run_current_loop_buck
from circuits.spice_utils import get_solve_count, reset_solve_counter, save_netlist
from scripts.stage6_common import (
    check_at_most,
    check_true,
    fmt,
    format_table,
    make_run,
    finish_run,
    summarize_checks,
)

STEP_S = 2e-8
WINDOW_S = 1e-3
DURATION_S = 6e-3


def _mean(time: np.ndarray, values: np.ndarray, window_s: float) -> float:
    return float(np.mean(values[time >= float(time[-1] - window_s)]))


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    controller = load_controller_config()
    power = charger.power_stage
    fixture = PackFixture.from_equivalent_voltage(11.4, power.path_resistance_ohm,
                                                  series_cells=charger.battery.series_cells,
                                                  model_id=charger.battery.identified_model_id)
    parameters = CurrentLoopParameters(
        kp_duty_per_a=controller.current_loop.kp,
        ki_duty_per_as=controller.current_loop.ki,
        anti_windup_per_s=controller.current_loop.kaw,
        duty_max=controller.duty_max,
        duty_min=controller.duty_min,
        soft_start_time_s=charger.charging.soft_start_time_s,
        switching_frequency_hz=power.switching_frequency_hz,
        diode_drop_v=power.diode_forward_voltage_estimate_v,
    )
    run_dir = make_run("stage6_current_loop")
    reset_solve_counter()

    cases = (
        ("IREF_1A", "DC 1.0", "DC 1"),
        ("IREF_0P5A", "DC 0.5", "DC 1"),
        ("ENABLE_DROP", "DC 1.0", step_expression(1, 0, 3e-3)),
    )
    rows = []
    measured = {}
    for name, reference, enable in cases:
        waveform, circuit, layout = run_current_loop_buck(
            power,
            fixture,
            parameters,
            duration_s=DURATION_S,
            step_s=STEP_S,
            current_reference_expression=reference,
            enable_expression=enable,
        )
        save_netlist(circuit, run_dir.path / f"netlist_{name.lower()}.cir")
        steady = _mean(waveform.time_s, waveform.charging_current_a, WINDOW_S)
        reference_command = (
            _mean(waveform.time_s, waveform.current_reference_a, WINDOW_S)
            if waveform.current_reference_a is not None
            else float("nan")
        )
        gate_after = _mean(waveform.time_s, waveform.gate_voltage_v, WINDOW_S)
        measured[name] = {
            "steady_current_a": steady,
            "reference_command_a": reference_command,
            "final_current_a": float(waveform.charging_current_a[-1]),
            "gate_mean_v": gate_after,
            "peak_current_a": float(waveform.charging_current_a.max()),
        }
        rows.append([name, fmt(reference_command, 4), fmt(steady, 5), fmt(gate_after, 4)])

    print("== 电流内环 ==")
    print(format_table(rows, ["工况", "指令A", "稳态A", "末段栅压均值V"]))

    checks = [
        check_at_most("iref_1a_steady_error_a", abs(measured["IREF_1A"]["steady_current_a"] - 1.0), 0.020, "A"),
        check_at_most("iref_0p5a_steady_error_a", abs(measured["IREF_0P5A"]["steady_current_a"] - 0.5), 0.020, "A"),
        check_at_most("enable_drop_residual_current_a", abs(measured["ENABLE_DROP"]["steady_current_a"]), 0.010, "A"),
        check_at_most("enable_drop_gate_v", abs(measured["ENABLE_DROP"]["gate_mean_v"]), 0.10, "V"),
        check_at_most("soft_start_overshoot_fraction",
                      max(0.0, measured["IREF_1A"]["peak_current_a"] - 1.0) / 1.0, 0.20, "1"),
        check_true("spice_solves_recorded", get_solve_count() >= 3, f"真实 ngspice 求解 {get_solve_count()} 次"),
    ]
    summary = summarize_checks(checks)
    payload = {
        "kind": "inner_current_loop",
        "layer": "spice_simulation",
        "step_s": STEP_S,
        "cases": measured,
        "spice_solves": get_solve_count(),
        **summary,
    }
    run_dir.write_config_snapshot(
        {"charger": charger.to_dict(), "controller": controller.to_dict(), "parameters": parameters.to_dict()}
    )
    finished = finish_run(run_dir, payload)
    print("\n== 检查 ==")
    for item in checks:
        print(f"  [{item.status:12s}] {item.name:34s} {fmt(item.measured):>12s}")
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"结果: {summary['status']}  PASS {summary['passed']}/{summary['total']}")
    return finished


if __name__ == "__main__":
    run()

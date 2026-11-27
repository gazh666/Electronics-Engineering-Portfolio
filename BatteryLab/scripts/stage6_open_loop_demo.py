"""第六阶段实验 2：Buck 功率级开环真实 SPICE（不含闭环控制）。

目的：先证明功率级本身可用，给闭环提供对照基线；开环结果不代表充电控制性能。

运行：conda run -n kaifa_battery python -m scripts.stage6_open_loop_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.charger_theory import calculate_buck_design
from analysis.charging_metrics import switching_period_average
from charging.config import load_charger_config
from circuits.charger_buck import PackFixture, run_open_loop_buck
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


def _window_mean(time: np.ndarray, values: np.ndarray, window_s: float) -> float:
    mask = time >= float(time[-1] - window_s)
    return float(np.mean(values[mask]))


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    power = charger.power_stage
    fixture = PackFixture.from_equivalent_voltage(11.4, power.path_resistance_ohm,
                                                  series_cells=charger.battery.series_cells,
                                                  model_id=charger.battery.identified_model_id)
    run_dir = make_run("stage6_open_loop")
    reset_solve_counter()

    rows = []
    results = {}
    for duty in (0.655, 0.66, 0.665):
        waveform, circuit, layout = run_open_loop_buck(
            power, fixture, duty=duty, duration_s=1.5e-3, step_s=STEP_S, vin_expression="DC 18"
        )
        save_netlist(circuit, run_dir.path / f"netlist_duty_{duty:.3f}.cir")
        _, current_average, current_ripple, _ = switching_period_average(
            waveform.time_s, waveform.inductor_current_a, power.switching_frequency_hz
        )
        _, voltage_average, voltage_ripple, _ = switching_period_average(
            waveform.time_s, waveform.pack_voltage_v, power.switching_frequency_hz
        )
        steady_current = _window_mean(waveform.time_s, waveform.charging_current_a, 0.5e-3)
        steady_voltage = _window_mean(waveform.time_s, waveform.pack_voltage_v, 0.5e-3)
        theory = calculate_buck_design(
            power.input_voltage_v,
            max(steady_voltage, 1.0),
            max(abs(steady_current), 0.05),
            power.inductance_h,
            power.capacitance_f,
            power.switching_frequency_hz,
            power.capacitor_esr_ohm,
        )
        rows.append(
            [
                f"{duty:.3f}",
                fmt(steady_voltage, 5),
                fmt(steady_current, 4),
                fmt(theory.inductor_ripple_a, 4),
                fmt(float(current_ripple.mean()), 4),
                fmt(float(voltage_ripple.mean()), 5),
            ]
        )
        results[duty] = {
            "steady_current_a": steady_current,
            "steady_voltage_v": steady_voltage,
            "theory_ripple_a": theory.inductor_ripple_a,
            "measured_current_ripple_a": float(current_ripple.mean()),
            "measured_voltage_ripple_v": float(voltage_ripple.mean()),
            "final_current_a": float(waveform.charging_current_a[-1]),
        }

    print("== 开环稳态 ==")
    print(format_table(rows, ["占空比", "末电压V", "末电流A", "理论电感纹波A", "实测电感纹波A", "电压纹波V"]))

    checks = []
    for duty, item in results.items():
        expected = duty * power.input_voltage_v
        relative = abs(item["steady_voltage_v"] - expected) / expected
        checks.append(check_at_most(f"vout_vs_D_vin_duty_{duty:.3f}", relative, 0.05, "1",
                                    "开环输出应接近 D·Vin（扣除二极管与 DCR 压降）"))
        checks.append(check_at_most(f"ripple_vs_theory_duty_{duty:.3f}",
                                    item["measured_current_ripple_a"] / item["theory_ripple_a"], 1.5, "1",
                                    "实测电感峰峰纹波 / 理论纹波"))
    ordered = [results[duty]["steady_current_a"] for duty in (0.655, 0.66, 0.665)]
    checks.append(check_true("current_increases_with_duty",
                             ordered[0] < ordered[1] < ordered[2], "开环占空比增益符号正确"))
    checks.append(check_at_most("open_loop_current_below_charge_oc",
                                max(ordered), 1.5, "A", "开环基线不触发第五阶段充电过流"))
    checks.append(check_true("spice_solves_recorded", get_solve_count() >= 3, f"真实 ngspice 求解 {get_solve_count()} 次"))

    summary = summarize_checks(checks)
    payload = {
        "kind": "open_loop_power_stage",
        "layer": "spice_simulation",
        "step_s": STEP_S,
        "cases": {f"{duty:.3f}": item for duty, item in results.items()},
        "spice_solves": get_solve_count(),
        **summary,
    }
    run_dir.write_config_snapshot({"charger": charger.to_dict(), "fixture": fixture.to_dict()})
    finished = finish_run(run_dir, payload)
    print("\n== 检查 ==")
    for item in checks:
        print(f"  [{item.status:12s}] {item.name:34s} {fmt(item.measured):>12s}")
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"结果: {summary['status']}  PASS {summary['passed']}/{summary['total']}")
    return finished


if __name__ == "__main__":
    run()

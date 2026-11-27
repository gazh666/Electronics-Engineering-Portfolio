"""第六阶段实验 1：Buck 功率级理论设计与平均模型趋势（无 SPICE）。

运行：conda run -n kaifa_battery python -m scripts.stage6_theory_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.charger_theory import calculate_buck_design, sweep_buck_designs
from charging.config import load_charger_config, load_controller_config
from scripts.stage6_common import (
    check_at_least,
    check_at_most,
    check_true,
    fmt,
    format_table,
    make_run,
    finish_run,
    summarize_checks,
)
from simulations.averaged_charger import AveragedChargerParameters, simulate_averaged_charge
from storage.result_store import write_csv


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    controller = load_controller_config()
    power = charger.power_stage
    run_dir = make_run("stage6_theory")

    rows = sweep_buck_designs(
        vin_v=power.input_voltage_v,
        output_voltages_v=(11.4, 11.95, 12.15),
        output_currents_a=(0.5, 1.0),
        inductances_h=(47e-6, 100e-6, 220e-6),
        capacitances_f=(100e-6, 220e-6, 470e-6),
        switching_frequency_hz=power.switching_frequency_hz,
        capacitor_esr_ohm=power.capacitor_esr_ohm,
    )
    header = list(rows[0])
    write_csv(run_dir.path / "buck_design_sweep.csv", header, ([row[key] for key in header] for row in rows))

    baseline = calculate_buck_design(
        power.input_voltage_v,
        charger.charging.constant_voltage_v,
        charger.charging.constant_current_a,
        power.inductance_h,
        power.capacitance_f,
        power.switching_frequency_hz,
        power.capacitor_esr_ohm,
    )
    print("== 设计点 ==")
    print(format_table(
        [[key, fmt(value)] for key, value in baseline.to_dict().items()],
        ["参数", "数值"],
    ))

    parameters = AveragedChargerParameters.from_configs(charger, controller).validate()
    averaged_rows = []
    for case_id, soc, duration in (
        ("AVG-C01", 0.63, 0.05),
        ("AVG-C02", 0.90, 0.05),
        ("AVG-C03", 0.80, 0.08),
    ):
        result = simulate_averaged_charge(parameters, initial_soc=soc, duration_s=duration, stop_at_termination=False)
        summary = result.summary()
        averaged_rows.append(
            [
                case_id,
                f"{soc:.2f}",
                fmt(summary["final_pack_voltage_v"], 5),
                fmt(summary["final_charging_current_a"], 4),
                fmt(summary["reached_cv"]),
                fmt(summary["voltage_overshoot_v"], 4),
                fmt(summary["soc_validity"]),
            ]
        )
    print("\n== 平均模型趋势（不是开关级证据）==")
    print(format_table(averaged_rows, ["工况", "初始SOC", "末电压V", "末电流A", "进入CV", "过冲V", "SOC区间"]))

    checks = [
        check_at_least("duty_below_limit", 1.0 - baseline.duty, 1.0 - controller.duty_max, "1",
                       "12.15 V 所需占空比必须低于 duty_max"),
        check_at_most("inductor_ripple_a", baseline.inductor_ripple_a, 0.8, "A",
                      "100 µH / 100 kHz / 18 V 下的理论纹波"),
        check_true("ccm_estimate", baseline.conduction_mode_estimate == "CCM_ESTIMATE",
                   "1 A 额定点应处于 CCM"),
        check_at_most("capacitor_voltage_ripple_v", baseline.capacitor_ripple_v + baseline.esr_ripple_v, 0.05, "V",
                      "容性纹波 + ESR 纹波"),
        check_true("averaged_model_reached_cv", any(row[4] == "YES" for row in averaged_rows),
                   "平均模型应能在足够高 SOC 下进入恒压"),
    ]
    summary = summarize_checks(checks)
    print("\n== 检查 ==")
    for item in checks:
        print(f"  [{item.status:12s}] {item.name:32s} {fmt(item.measured):>12s} {item.unit}")

    payload = {
        "kind": "theory_and_averaged_model",
        "layer": "analytical_theory + averaged_simulation",
        "design": baseline.to_dict(),
        "sweep_rows": len(rows),
        "averaged_cases": [row for row in averaged_rows],
        **summary,
    }
    run_dir.write_config_snapshot({"charger": charger.to_dict(), "controller": controller.to_dict()})
    finished = finish_run(run_dir, payload)
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"结果: {summary['status']}  PASS {summary['passed']}/{summary['total']}")
    return finished


if __name__ == "__main__":
    run()

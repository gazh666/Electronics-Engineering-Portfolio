"""第六阶段实验 7：双闭环小信号稳定裕度与 PI 整定筛选（平均模型/线性化）。

结论层次是"平均模型 + 线性化"，不是开关级稳定性证明；开关级复核在 C01–C03。

运行：conda run -n kaifa_battery python -m scripts.stage6_loop_analysis_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.charging_loop_analysis import (
    analyze_current_loop,
    analyze_voltage_loop,
    bandwidth_separation_ratio,
    default_frequency_grid,
)
from charging.battery_adapter import load_identified_battery_bundle
from charging.config import load_charger_config, load_controller_config, load_tuning_grid
from scripts.stage6_common import (
    check_at_least,
    check_true,
    fmt,
    format_table,
    make_run,
    finish_run,
    summarize_checks,
)


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    controller = load_controller_config()
    power = charger.power_stage
    bundle = load_identified_battery_bundle(charger.battery.identified_model_id)
    cells = charger.battery.series_cells
    r0 = cells * float(bundle["parameters"].r0_ohm)
    r1 = cells * float(bundle["parameters"].r1_ohm)
    c1 = float(bundle["parameters"].c1_f) / cells
    # 充电负载是刚性电池：输出端等效为 R0_pack + 通路电阻，而不是 12 V/1 A 电阻。
    # 若误用 Vout/I 作为负载，会把电流环穿越频率低估约 40 倍。
    load = r0 + power.path_resistance_ohm

    grid = default_frequency_grid()
    current_loop = analyze_current_loop(
        grid,
        vin_v=power.input_voltage_v,
        inductance_h=power.inductance_h,
        capacitance_f=power.capacitance_f,
        load_resistance_ohm=load,
        capacitor_esr_ohm=power.capacitor_esr_ohm,
        kp_duty_per_a=controller.current_loop.kp,
        ki_duty_per_as=controller.current_loop.ki,
        inductor_dc_resistance_ohm=power.inductor_dcr_ohm,
    )
    voltage_loop = analyze_voltage_loop(
        grid,
        battery_r0_ohm=r0,
        battery_r1_ohm=r1,
        battery_c1_f=c1,
        kp_a_per_v=controller.voltage_loop.kp,
        ki_a_per_vs=controller.voltage_loop.ki,
        inner_loop_gain=current_loop["loop_gain"],
    )
    voltage_loop_ideal = analyze_voltage_loop(
        grid, r0, r1, c1, controller.voltage_loop.kp, controller.voltage_loop.ki
    )
    ratio = bandwidth_separation_ratio(current_loop, voltage_loop)

    frozen_rows = [
        ["电流环", fmt(current_loop["gain_crossover_hz"], 6), fmt(current_loop["phase_margin_deg"], 5),
         fmt(current_loop["gain_margin_db"], 5) if not current_loop["gain_margin_infinite"] else "INF",
         fmt(current_loop["minimum_phase_deg"], 5)],
        ["电压环", fmt(voltage_loop["gain_crossover_hz"], 6), fmt(voltage_loop["phase_margin_deg"], 5),
         fmt(voltage_loop["gain_margin_db"], 5) if not voltage_loop["gain_margin_infinite"] else "INF",
         fmt(voltage_loop["minimum_phase_deg"], 5)],
    ]
    print("== 冻结增益下的裕度（平均模型）==")
    print(format_table(frozen_rows, ["环路", "穿越Hz", "相位裕度deg", "增益裕度dB", "最小相位deg"]))
    print(f"带宽分离比（电流/电压）：{fmt(ratio, 4)}")

    grid_config = load_tuning_grid()
    sweep_rows = []
    best = []
    for kp in grid_config["voltage_kp"]:
        for ki in grid_config["voltage_ki"]:
            candidate = analyze_voltage_loop(
                grid, r0, r1, c1, kp, ki, inner_loop_gain=current_loop["loop_gain"]
            )
            pm = candidate["phase_margin_deg"]
            fc = candidate["gain_crossover_hz"]
            separation = bandwidth_separation_ratio(current_loop, candidate)
            sweep_rows.append([fmt(kp, 4), fmt(ki, 6), fmt(fc, 5), fmt(pm, 5), fmt(separation, 4)])
            if pm is not None and fc is not None and separation is not None and pm >= 45.0 and separation >= 5.0:
                best.append((kp, ki, fc, pm, separation))
    print("\n== 电压环整定网格 ==")
    print(format_table(sweep_rows, ["kp", "ki", "fc Hz", "PM deg", "带宽分离"]))
    print(
        f"理想电流源内环下电压环 fc={fmt(voltage_loop_ideal['gain_crossover_hz'], 6)} Hz，"
        f"PM={fmt(voltage_loop_ideal['phase_margin_deg'], 5)}°（用于对比内环相位滞后的影响）"
    )

    def margin_check(name: str, item: dict, limit: float) -> object:
        if item.get("gain_margin_infinite"):
            return check_true(name, True, "无相位穿越，增益裕度视为无穷（仅下限类指标允许）")
        return check_at_least(name, item.get("gain_margin_db"), limit, "dB")

    frozen_ok = (
        controller.voltage_loop.kp,
        controller.voltage_loop.ki,
    ) in {(item[0], item[1]) for item in best}
    checks = [
        check_at_least("current_phase_margin_deg", current_loop["phase_margin_deg"], 45.0, "deg"),
        margin_check("current_gain_margin_db", current_loop, 6.0),
        check_at_least("voltage_phase_margin_deg", voltage_loop["phase_margin_deg"], 45.0, "deg"),
        margin_check("voltage_gain_margin_db", voltage_loop, 6.0),
        check_at_least("bandwidth_separation_ratio", ratio, 5.0, "1"),
        check_true("frozen_gains_in_feasible_grid", bool(frozen_ok),
                   "冻结的电压环 kp/ki 必须来自满足 PM>=45° 且带宽分离>=5 的网格点"),
    ]
    summary = summarize_checks(checks)
    payload = {
        "kind": "loop_margins",
        "layer": "averaged_simulation_linearized",
        "current_loop": {key: value for key, value in current_loop.items() if key not in ("loop_gain", "plant")},
        "voltage_loop": {key: value for key, value in voltage_loop.items() if key not in ("loop_gain", "plant")},
        "bandwidth_separation_ratio": ratio,
        "tuning_grid_rows": len(sweep_rows),
        "feasible_points": [list(item) for item in best],
        **summary,
    }
    run_dir = make_run("stage6_loop_analysis")
    run_dir.write_config_snapshot({"charger": charger.to_dict(), "controller": controller.to_dict()})
    finished = finish_run(run_dir, payload)
    print("\n== 检查 ==")
    for item in checks:
        print(f"  [{item.status:12s}] {item.name:34s} {fmt(item.measured):>12s}")
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"结果: {summary['status']}  PASS {summary['passed']}/{summary['total']}")
    return finished


if __name__ == "__main__":
    run()

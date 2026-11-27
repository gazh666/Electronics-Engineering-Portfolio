"""第五阶段实验 1：背靠背 MOSFET 导通、双向阻断与瞬态切断（真实 ngspice）。

运行：conda run -n kaifa_battery python -m scripts.protection_switch_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from circuits.gate_driver import analyze_gate_drive, run_gate_driver_spice
from circuits.protection_mosfet import run_switch_case_matrix, run_turn_off_transient
from circuits.spice_utils import get_solve_count, reset_solve_counter
from scripts.stage5_common import (
    check_at_most,
    check_within,
    check_true,
    stage5_limits,
    summarize_checks,
)
from storage.result_store import RunDirectory, write_json
from visualization.plots import plot_xy


def run(root: Path | None = None) -> dict:
    reset_solve_counter()
    limits = stage5_limits()
    run_dir = RunDirectory("protection", root=root)
    run_dir.write_metadata(
        {
            "stage": "stage5",
            "experiment": "back_to_back_mosfet_switch",
            "spice_backend": "ngspice via PySpice",
            "cell_r0_ohm": 0.077068,
            "cell_ocv_v": 4.05,
            "note": "教学 level-1 MOSFET 模型，不是真实器件晶体管级模型",
        }
    )
    run_dir.write_config_snapshot({"protection_config": limits.to_dict()})

    cases = run_switch_case_matrix(limits)
    transient = run_turn_off_transient(limits)

    case_rows = []
    for case in cases:
        row = case.to_dict()
        row.pop("node_voltages_v")
        case_rows.append(row)
    write_json(run_dir.path / "switch_cases.json", [case.to_dict() for case in cases])
    run_dir.write_waveform(
        list(case_rows[0].keys()), [[row[key] for key in case_rows[0]] for row in case_rows],
        name="switch_cases.csv",
    )
    run_dir.write_waveform(
        ["time_s", "discharge_current_a", "gate_voltage_v", "switch_voltage_v"],
        [
            (time, current, gate, voltage)
            for time, current, gate, voltage in zip(
                transient.time_s.tolist(),
                transient.discharge_current_a.tolist(),
                transient.gate_voltage_v.tolist(),
                transient.switch_voltage_v.tolist(),
            )
        ],
        name="turn_off_waveform.csv",
    )

    netlist_path = run_dir.path / "protection_switch.cir"
    from circuits.protection_mosfet import build_back_to_back_circuit

    build = build_back_to_back_circuit(
        limits, charge_fet_on=True, discharge_fet_on=True, load_ohm=11.8, charger_voltage_v=12.6
    )
    netlist_path.write_text(str(build), encoding="utf-8")

    plot_xy(
        transient.time_s,
        transient.discharge_current_a,
        path=run_dir.path / "plots" / "turn_off_current.png",
        xlabel="时间 / s",
        ylabel="放电电流 / A",
        title="背靠背 MOSFET 同时关断：电流切断",
        annotation=f"切断时刻={transient.current_cutoff_time_s}",
    )
    plot_xy(
        transient.time_s,
        transient.gate_voltage_v,
        path=run_dir.path / "plots" / "turn_off_gate.png",
        xlabel="时间 / s",
        ylabel="Vgs / V",
        title="放电管栅极电压（相对共源节点）",
    )

    by_case = {case.case: case for case in cases}
    a = by_case["CASE_A_BOTH_ON_DISCHARGE"]
    c = by_case["CASE_C_CHG_OFF_BLOCK_CHARGE"]
    d = by_case["CASE_D_DSG_OFF_BLOCK_DISCHARGE"]
    e = by_case["CASE_E_BOTH_OFF_LEAKAGE"]
    f = by_case["CASE_F_INPUT_COLLAPSE_BOTH_ON"]
    g = by_case["CASE_G_INPUT_COLLAPSE_DSG_OFF"]

    gate_analysis = analyze_gate_drive(limits, fet_count=2)
    gate_spice = run_gate_driver_spice(limits)
    write_json(
        run_dir.path / "gate_drive.json",
        {
            "analytic": gate_analysis.to_dict(),
            "spice": {
                "steady_gate_voltage_v": gate_spice["steady_gate_voltage_v"],
                "measured_peak_current_a": gate_spice["measured_peak_current_a"],
                "measured_rise_time_s": gate_spice["measured_rise_time_s"],
            },
        },
    )

    verdicts = [
        check_at_most(
            "1 A 放电导通压降",
            abs(a.switch_drop_v),
            0.060,
            "V",
            "两只 FET 串联，单管约 18.7 mΩ",
        ),
        check_at_most("充电管关断后充电电流", abs(c.charge_current_a), 0.001, "A"),
        check_at_most("放电管关断后放电电流", abs(d.load_current_a), 0.001, "A"),
        check_at_most("双管关断反向漏电", abs(e.switch_current_a), 1e-6, "A"),
        check_true("输入掉电时双管导通会回灌", abs(f.switch_current_a) > 1.0, f"{f.switch_current_a:.3f} A"),
        check_at_most("输入掉电且放电管关断时回灌", abs(g.switch_current_a), 0.001, "A"),
        check_true(
            "瞬态切断完成",
            transient.current_cutoff_time_s is not None
            and abs(float(transient.discharge_current_a[-1])) < 0.01,
            f"切断={transient.current_cutoff_time_s}",
        ),
        check_within(
            "栅极峰值电流相对误差",
            (gate_spice["measured_peak_current_a"] - gate_analysis.peak_gate_current_a)
            / gate_analysis.peak_gate_current_a,
            0.05,
            "-",
        ),
        check_within(
            "栅极上升时间相对误差",
            (gate_spice["measured_rise_time_s"] - gate_analysis.theoretical_rise_time_s)
            / gate_analysis.theoretical_rise_time_s,
            0.15,
            "-",
        ),
    ]

    summary = {
        "run_id": run_dir.run_id,
        "real_spice_solves": get_solve_count(),
        "case_count": len(cases),
        "on_state_resistance_ohm": a.switch_resistance_ohm,
        "per_device_resistance_ohm": a.switch_resistance_ohm / 2.0,
        "turn_off": transient.summary(),
        "gate_drive": {
            "analytic": gate_analysis.to_dict(),
            "measured_peak_current_a": gate_spice["measured_peak_current_a"],
            "measured_rise_time_s": gate_spice["measured_rise_time_s"],
        },
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
    print(f"real_spice_solves={result['summary']['real_spice_solves']}")
    for check in verdict["checks"]:
        print(f"{check['status']:4s} {check['name']:32s} measured={check['measured']} limit={check['limit']}")
    print(f"total PASS={verdict['passed']} FAIL={verdict['failed']}")
    return 0 if verdict["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())



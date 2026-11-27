"""第六阶段实验 4：网表内双闭环 CC / CV / CC→CV 切换（C01–C03）。

运行：conda run -n kaifa_battery python -m scripts.stage6_cascade_cccv_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charging.config import load_charger_config, load_controller_config
from circuits.spice_utils import reset_solve_counter, get_solve_count
from scripts.stage6_common import fmt, format_table, make_run, finish_run
from simulations.averaged_charger import (
    AveragedChargerParameters,
    compare_with_switching,
    simulate_averaged_charge,
)
from simulations.charger_spice_runner import run_case


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    controller = load_controller_config()
    averaged_parameters = AveragedChargerParameters.from_configs(charger, controller).validate()
    run_dir = make_run("stage6_cascade_cccv")
    reset_solve_counter()

    cases = (("C01", 0.63), ("C02", 0.90), ("C03", 0.80))
    rows = []
    payload = {}
    failed = []
    for case_id, equivalent_soc in cases:
        result = run_case(case_id, charger=charger, controller=controller, persist=True)
        summary = result.summary
        averaged = simulate_averaged_charge(
            averaged_parameters,
            initial_soc=equivalent_soc,
            duration_s=summary["duration_s"],
            stop_at_termination=False,
        )
        comparison = compare_with_switching(averaged, summary)
        payload[case_id] = {
            "switching": {
                key: summary.get(key)
                for key in (
                    "steady_current_a",
                    "steady_pack_voltage_v",
                    "max_charging_current_a",
                    "cc_mean_error_a",
                    "cv_mean_error_v",
                    "reached_cv",
                    "transition_time_s",
                    "voltage_overshoot_v",
                    "case_status",
                )
            },
            "averaged": averaged.summary(),
            "comparison": comparison,
            "checks": result.checks,
            "run_dir": None if result.run_dir is None else str(result.run_dir.path),
        }
        if summary["case_status"] != "PASS":
            failed.append(case_id)
        rows.append(
            [
                case_id,
                fmt(summary.get("steady_current_a"), 5),
                fmt(summary.get("steady_pack_voltage_v"), 5),
                fmt(summary.get("reached_cv")),
                fmt(summary.get("transition_time_s"), 4),
                fmt(summary.get("voltage_overshoot_v"), 4),
                fmt(averaged.summary()["final_charging_current_a"], 5),
                summary["case_status"],
            ]
        )

    print("== CC-CV 开关级结果（真实 ngspice）==")
    print(format_table(rows, ["工况", "末电流A", "末电压V", "CV", "切换s", "过冲V", "平均模型A", "判定"]))

    checks = []
    for item in payload.values():
        checks.extend(item["checks"])
    summary = {
        "kind": "cascade_cccv",
        "layer": "spice_simulation",
        "cases": payload,
        "spice_solves": get_solve_count(),
        "failed_cases": failed,
        "status": "PASS" if not failed else "FAIL",
    }
    finished = finish_run(run_dir, summary)
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"结果: {summary['status']}  失败工况 {failed or '无'}")
    return finished


if __name__ == "__main__":
    run()

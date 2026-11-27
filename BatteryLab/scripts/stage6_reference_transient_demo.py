"""第六阶段实验 6：电流指令阶跃、BMS 禁止充电、DCM 与反向供电（C08–C10、C19、C20）。

运行：conda run -n kaifa_battery python -m scripts.stage6_reference_transient_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charging.config import load_charger_config, load_controller_config
from circuits.spice_utils import get_solve_count, reset_solve_counter
from scripts.stage6_common import fmt, format_table, make_run, finish_run
from simulations.charger_spice_runner import run_case


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    controller = load_controller_config()
    run_dir = make_run("stage6_reference_transient")
    reset_solve_counter()

    case_ids = ("C08", "C09", "C10", "C19", "C20")
    rows = []
    payload = {}
    failed = []
    for case_id in case_ids:
        result = run_case(case_id, charger=charger, controller=controller, persist=True)
        summary = result.summary
        payload[case_id] = {
            "steady_current_a": summary.get("steady_current_a"),
            "expected_steady_current_a": summary.get("expected_steady_current_a"),
            "gate_activity_after_disable_v": summary.get("gate_activity_after_disable_v"),
            "conduction_mode_estimate": summary.get("conduction_mode_estimate"),
            "max_reverse_current_a": summary.get("max_reverse_current_a"),
            "case_status": summary.get("case_status"),
            "checks": result.checks,
            "run_dir": None if result.run_dir is None else str(result.run_dir.path),
        }
        if summary["case_status"] != "PASS":
            failed.append(case_id)
        rows.append(
            [
                case_id,
                fmt(summary.get("steady_current_a"), 5),
                fmt(summary.get("expected_steady_current_a"), 4),
                fmt(summary.get("gate_activity_after_disable_v"), 4),
                fmt(summary.get("conduction_mode_estimate")),
                fmt(summary.get("max_reverse_current_a"), 4),
                summary.get("case_status"),
            ]
        )

    print("== 指令阶跃 / 禁止充电 / DCM / 反向供电（真实 ngspice）==")
    print(format_table(rows, ["工况", "稳态A", "期望A", "关断后栅压V", "导通模式", "最大反向A", "判定"]))

    checks = []
    for item in payload.values():
        checks.extend(item["checks"])
    summary = {
        "kind": "reference_transient",
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

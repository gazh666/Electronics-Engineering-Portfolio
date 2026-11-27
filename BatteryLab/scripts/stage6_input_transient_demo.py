"""第六阶段实验 5：输入电压扰动与掉电（C04–C07）。

运行：conda run -n kaifa_battery python -m scripts.stage6_input_transient_demo
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
    run_dir = make_run("stage6_input_transient")
    reset_solve_counter()

    rows = []
    payload = {}
    failed = []
    for case_id in ("C04", "C05", "C06", "C07"):
        result = run_case(case_id, charger=charger, controller=controller, persist=True)
        summary = result.summary
        payload[case_id] = {
            "steady_current_a": summary.get("steady_current_a"),
            "expected_steady_current_a": summary.get("expected_steady_current_a"),
            "final_pack_voltage_v": summary.get("final_pack_voltage_v"),
            "max_reverse_current_a": summary.get("max_reverse_current_a"),
            "protection": summary.get("protection"),
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
                fmt(summary.get("final_pack_voltage_v"), 5),
                fmt(summary.get("max_reverse_current_a"), 4),
                "YES" if summary.get("protection", {}).get("latched_faults") else "NO",
                summary.get("case_status"),
            ]
        )

    print("== 输入扰动（真实 ngspice）==")
    print(format_table(rows, ["工况", "阶跃前/后稳态A", "末电压V", "最大反向A", "保护锁存", "判定"]))

    checks = []
    for item in payload.values():
        checks.extend(item["checks"])
    summary = {
        "kind": "input_transient",
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

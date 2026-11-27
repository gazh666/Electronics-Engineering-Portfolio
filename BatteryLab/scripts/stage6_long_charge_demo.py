"""第六阶段实验 9：ECM 长时充电包络（终止判定与最大时间）。

层次：秒级准静态 ECM，不是开关级；开关级 CC–CV 由 C01–C03 覆盖。

运行：conda run -n kaifa_battery python -m scripts.stage6_long_charge_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charging.config import load_charging_cases
from scripts.stage6_common import fmt, format_table, make_run, finish_run
from simulations.charging_experiments import run_experiment


def run(root: Path | None = None) -> dict:
    run_dir = make_run("stage6_long_charge")
    cases = {case.id: case for case in load_charging_cases()}

    rows = []
    payload = {}
    failed = []
    for case_id in ("C14", "C16"):
        result = run_experiment(cases[case_id])
        summary = result["summary"]
        payload[case_id] = {
            "state": summary.get("state"),
            "termination_reason": summary.get("termination_reason"),
            "duration_s": summary.get("duration_s"),
            "final_pack_voltage_v": summary.get("final_pack_voltage_v"),
            "final_charging_current_a": summary.get("final_charging_current_a"),
            "charge_ah": summary.get("charge_ah"),
            "final_soc_mean": summary.get("final_soc_mean"),
            "energy": summary.get("energy"),
            "checks": result["checks"],
            "status": result["status"],
        }
        if result["status"] != "PASS":
            failed.append(case_id)
        rows.append(
            [
                case_id,
                fmt(summary.get("state")),
                fmt(summary.get("termination_reason")),
                fmt(summary.get("duration_s"), 6),
                fmt(summary.get("final_pack_voltage_v"), 5),
                fmt(summary.get("final_charging_current_a"), 4),
                fmt(summary.get("charge_ah"), 5),
                result["status"],
            ]
        )

    print("== 长时充电包络 ==")
    print(format_table(rows, ["工况", "终态", "终止原因", "时长s", "末电压V", "末电流A", "充入Ah", "判定"]))
    for case_id, item in payload.items():
        print(f"\n{case_id} 能量: {item['energy']}")

    summary_payload = {
        "kind": "long_duration_envelope",
        "layer": "ecm_charge_envelope + behavioral_charging_simulation",
        "cases": payload,
        "failed_cases": failed,
        "status": "PASS" if not failed else "FAIL",
    }
    finished = finish_run(run_dir, summary_payload)
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"结果: {summary_payload['status']}  失败工况 {failed or '无'}")
    return finished


if __name__ == "__main__":
    run()

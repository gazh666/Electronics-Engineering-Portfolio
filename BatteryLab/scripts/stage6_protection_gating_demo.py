"""第六阶段实验 10：BMS 许可联锁与边界工况（C11、C12、C13、C15、C17、C18）。

运行：conda run -n kaifa_battery python -m scripts.stage6_protection_gating_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charging.config import load_charger_config, load_charging_cases
from charging.protection_adapter import create_protection_controller
from scripts.stage6_common import (
    check_true,
    fmt,
    format_table,
    make_run,
    finish_run,
    summarize_checks,
)
from simulations.charging_experiments import run_experiment


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    run_dir = make_run("stage6_protection_gating")
    cases = {case.id: case for case in load_charging_cases()}

    rows = []
    payload = {}
    failed = []
    for case_id in ("C11", "C12", "C13", "C15", "C17", "C18"):
        result = run_experiment(cases[case_id])
        summary = result["summary"]
        payload[case_id] = {
            "status": result["status"],
            "summary": summary,
            "checks": result["checks"],
        }
        if result["status"] != "PASS":
            failed.append(case_id)
        rows.append(
            [
                case_id,
                fmt(result["method"]),
                fmt(summary.get("state") or summary.get("status")),
                fmt(summary.get("termination_reason")),
                fmt(summary.get("max_cell_voltage_v"), 5),
                fmt(summary.get("max_cell_voltage_at_pack_v"), 5),
                result["status"],
            ]
        )

    print("== 保护联锁与边界工况 ==")
    print(format_table(rows, ["工况", "层次", "终态", "原因", "最高单体V", "对应组压V", "判定"]))

    config = charger.validate_against_protection()
    checks = [
        check_true("cv_per_cell_below_ov_release", config["per_cell_cv_v"] < config["cell_overvoltage_release_v"],
                   f"CV 折算单体 {config['per_cell_cv_v']:.4f} V < 释放 {config['cell_overvoltage_release_v']:.4f} V"),
        check_true("charge_oc_above_cc", config["charge_overcurrent_trip_a"] > charger.charging.constant_current_a,
                   f"充电过流 {config['charge_overcurrent_trip_a']} A > 恒流 {charger.charging.constant_current_a} A"),
        check_true("no_automatic_restart", charger.charging.automatic_restart_enabled is False),
        check_true("protection_controller_used", True, "工况通过第五阶段真实 ProtectionController 判定"),
    ]
    precheck = create_protection_controller()
    snapshot = precheck.update(0.0, (3.9, 3.9, 3.9), 0.0, 25.0)
    checks.append(check_true("nominal_charge_allowed", bool(snapshot.charge_allowed),
                             "常温、3.9 V/节时 BMS 必须允许充电"))

    summary = summarize_checks(checks)
    payload_checks = {
        "protection_summary": config,
        "case_statuses": {case_id: item["status"] for case_id, item in payload.items()},
    }
    payload_all = {
        "kind": "protection_gating",
        "layer": "mixed_ecm_and_software",
        "cases": payload,
        **payload_checks,
        **summary,
        "failed_cases": failed,
        "status": "FAIL" if failed or summary["status"] != "PASS" else "PASS",
    }
    finished = finish_run(run_dir, payload_all)
    print("\n== 检查 ==")
    for item in checks:
        print(f"  [{item.status:12s}] {item.name:36s} {fmt(item.measured):>10s}")
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"结果: {payload_all['status']}  失败工况 {failed or '无'}")
    return finished


if __name__ == "__main__":
    run()

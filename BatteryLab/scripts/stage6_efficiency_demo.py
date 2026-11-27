"""第六阶段实验 8：充电功率级损耗与效率（真实 SPICE + 功率守恒）。

运行：conda run -n kaifa_battery python -m scripts.stage6_efficiency_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charging.config import load_charger_config, load_controller_config
from circuits.spice_utils import get_solve_count, reset_solve_counter
from scripts.stage6_common import (
    check_at_least,
    check_at_most,
    fmt,
    format_table,
    make_run,
    finish_run,
    summarize_checks,
)
from simulations.charger_spice_runner import run_case


def run(root: Path | None = None) -> dict:
    charger = load_charger_config()
    controller = load_controller_config()
    run_dir = make_run("stage6_efficiency")
    reset_solve_counter()

    result = run_case("C01", charger=charger, controller=controller, persist=True)
    summary = result.summary
    losses = summary["losses"]
    energy = summary["energy"]
    efficiency = summary["efficiency"]

    rows = [[name, fmt(value, 5)] for name, value in losses.items()]
    print("== 功率级损耗分解（C01 稳态窗口）==")
    print(format_table(rows, ["损耗项", "功率W"]))
    print(
        f"\n输入 {fmt(efficiency['input_power_w'], 5)} W / 电池 {fmt(efficiency['battery_power_w'], 5)} W / "
        f"效率 {fmt(efficiency['power_stage_efficiency_percent'], 5)}%"
    )
    print(
        f"功率守恒残差 {fmt(summary['power_conservation_residual_fraction'], 4)} / "
        f"ZOH-梯形积分差 {fmt(summary['intrinsic_solver_consistency_ppm'], 4)} ppm"
    )

    checks = [
        check_at_least("power_stage_efficiency_min_percent", efficiency["power_stage_efficiency_percent"], 85.0, "%"),
        check_at_most("power_conservation_residual_fraction",
                      abs(summary["power_conservation_residual_fraction"]), 0.01, "1"),
        check_at_most("intrinsic_solver_consistency_ppm", abs(summary["intrinsic_solver_consistency_ppm"]), 100.0, "ppm"),
        check_at_most("energy_integration_gap_percent", abs(energy["integration_gap_percent"] or 0.0), 0.01, "%"),
    ]
    summary_payload = summarize_checks(checks)
    payload = {
        "kind": "efficiency",
        "layer": "spice_simulation",
        "case_id": "C01",
        "losses": losses,
        "efficiency": efficiency,
        "energy": energy,
        "power_conservation_residual_fraction": summary["power_conservation_residual_fraction"],
        "spice_solves": get_solve_count(),
        "case_run_dir": None if result.run_dir is None else str(result.run_dir.path),
        **summary_payload,
    }
    run_dir.write_config_snapshot({"charger": charger.to_dict(), "controller": controller.to_dict()})
    finished = finish_run(run_dir, payload)
    print("\n== 检查 ==")
    for item in checks:
        print(f"  [{item.status:12s}] {item.name:36s} {fmt(item.measured):>12s}")
    print(f"\n运行目录: {finished['run_dir']}")
    print(f"结果: {summary_payload['status']}  PASS {summary_payload['passed']}/{summary_payload['total']}")
    return finished


if __name__ == "__main__":
    run()

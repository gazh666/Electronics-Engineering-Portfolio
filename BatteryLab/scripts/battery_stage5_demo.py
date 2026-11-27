"""第五阶段综合验收：串联四个真实实验并给出统一 PASS/FAIL。

运行：conda run -n kaifa_battery python -m scripts.battery_stage5_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from battery_models.parameters import load_yaml
from protection.limits import load_limits
from scripts import (
    balancing_demo,
    protection_state_machine_demo,
    protection_switch_demo,
    protection_threshold_demo,
)
from scripts.stage5_common import Check, check_at_most, check_true, summarize_checks
from storage.result_store import RunDirectory, write_csv, write_json


def run(root: Path | None = None) -> dict:
    limits = load_limits()
    run_dir = RunDirectory("stage5_validation", root=root)
    run_dir.write_metadata(
        {
            "stage": "stage5",
            "description": "3S MOSFET 保护、故障状态机与被动均衡综合验收",
            "hardware_validation": False,
            "note": "全部为真实 ngspice 求解与冻结 ECM 数值实验，不是硬件实测",
        }
    )

    module_results = {
        "switch": protection_switch_demo.run(root),
        "threshold": protection_threshold_demo.run(root),
        "state_machine": protection_state_machine_demo.run(root),
        "balancing": balancing_demo.run(root),
    }

    checks: list[Check] = []
    for result in module_results.values():
        checks.extend(result["checks"])

    afe = load_yaml(PROJECT_ROOT / "configs" / "afe_config.yaml")
    afe_min = float(afe["cell_voltage"]["measurement_min_v"])
    afe_max = float(afe["cell_voltage"]["measurement_max_v"])
    checks.extend(
        [
            check_true(
                "未收紧第四阶段单体采集下限",
                limits.afe_measurement_min_v <= afe_min and limits.cell_undervoltage_trip_v >= afe_min,
                f"AFE={afe_min}..{afe_max}, UV={limits.cell_undervoltage_trip_v}",
            ),
            check_true(
                "未收紧第四阶段单体采集上限",
                limits.afe_measurement_max_v >= afe_max and limits.cell_overvoltage_trip_v <= afe_max,
                f"AFE={afe_min}..{afe_max}, OV={limits.cell_overvoltage_trip_v}",
            ),
            check_at_most(
                "真实 SPICE 求解总数（预算 40）",
                float(
                    sum(result["summary"].get("real_spice_solves", 0) for result in module_results.values())
                ),
                40.0,
                "次",
            ),
            check_true(
                "恢复后必须重新使能（禁止自动重启）",
                limits.automatic_restart is False,
                "状态机单测与时间线共同验证",
            ),
        ]
    )

    for module_name, result in module_results.items():
        run_dir.log(f"{module_name}: run={result['run_id']} path={result['path']}")

    verdict = summarize_checks(checks)
    write_csv(
        run_dir.path / "validation_checks.csv",
        ["name", "measured", "limit", "unit", "status", "note"],
        [
            (item.name, item.measured, item.limit, item.unit, item.status, item.note)
            for item in checks
        ],
    )
    write_json(
        run_dir.path / "module_runs.json",
        {
            name: {
                "run_id": result["run_id"],
                "path": result["path"],
                "real_spice_solves": result["summary"].get("real_spice_solves"),
                "status": result["summary"].get("verdict", {}).get("status"),
            }
            for name, result in module_results.items()
        },
    )
    total_spice = sum(result["summary"].get("real_spice_solves", 0) for result in module_results.values())
    summary = {
        "run_id": run_dir.run_id,
        "stage": "stage5",
        "status": verdict["status"],
        "passed": verdict["passed"],
        "failed": verdict["failed"],
        "total": verdict["total"],
        "real_spice_solves": total_spice,
        "modules": {name: result["run_id"] for name, result in module_results.items()},
        "checks": verdict["checks"],
        "limits": limits.to_dict(),
        "threshold_provenance": limits.threshold_provenance(),
        "limitations": [
            "MOSFET 为 level-1 教学模型，不是真实器件晶体管级模型",
            "比较器为分立元件等效，不是商业保护 IC 内部电路",
            "均衡温升为一阶 Rth 估算，未做热仿真",
            "未做真实电池充放电、过充或短路实验",
            "未验证真实 PCB 寄生、EMI 与器件批次差异",
        ],
    }
    run_dir.write_summary(summary)
    run_dir.flush_log()
    return {"run_id": run_dir.run_id, "summary": summary, "checks": checks, "path": str(run_dir.path)}


def main() -> int:
    result = run()
    summary = result["summary"]
    print(f"run_id={result['run_id']}")
    for check in summary["checks"]:
        print(f"{check['status']:4s} {check['name']:34s} measured={check['measured']} limit={check['limit']}")
    print(f"total PASS={summary['passed']} FAIL={summary['failed']} SPICE={summary['real_spice_solves']}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

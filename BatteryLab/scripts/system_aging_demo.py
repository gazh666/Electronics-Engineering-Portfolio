"""任务 21：容量衰减与内阻增长对运行时间的影响。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.system_runtime import runtime_summary  # noqa: E402
from integration.battery_port_adapter import build_battery_port  # noqa: E402
from integration.protection_adapter import ProtectionGate  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, new_run_dir, write_json  # noqa: E402
from scripts.system_discharge_demo import latest_power_map_file, load_maps  # noqa: E402
from system_models.long_duration_system import simulate_discharge  # noqa: E402
from validation.system_result_judge import compile_case_result, judge  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="老化敏感性")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--load-a", type=float, default=1.5)
    parser.add_argument("--dt-s", type=float, default=5.0)
    parser.add_argument("--max-duration-s", type=float, default=8 * 3600.0)
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir))
        if args.run_dir
        else new_run_dir(STAGE9_RESULTS / "system_lifetime", "aging")
    )
    directory.mkdir(parents=True, exist_ok=True)

    map_file = latest_power_map_file()
    if map_file is None:
        summary = {"run_id": run_id, "status": "BLOCKED", "reason": "缺少真实功率映射"}
        write_json(directory / "case_result.json", summary)
        if args.json_out:
            write_json(args.json_out, summary)
        print(json.dumps({"run_id": run_id, "status": "BLOCKED"}, ensure_ascii=False))
        return 1
    maps = load_maps(map_file.parent)
    if args.load_a not in maps:
        available = sorted(maps)
        if not available:
            summary = {"run_id": run_id, "status": "BLOCKED", "reason": "映射为空"}
            write_json(directory / "case_result.json", summary)
            print(json.dumps({"run_id": run_id, "status": "BLOCKED"}, ensure_ascii=False))
            return 1
        args.load_a = available[len(available) // 2]
    power_map = maps[args.load_a]

    base_capacity = 2.0280827046460144
    scenarios = [
        ("soh_100", base_capacity * 1.00, 1.00),
        ("soh_90", base_capacity * 0.90, 1.25),
        ("soh_80", base_capacity * 0.80, 1.50),
    ]
    records = []
    reference_runtime = None
    for name, capacity, r0_scale in scenarios:
        port = build_battery_port(
            initial_soc=(0.4, 0.4, 0.4),
            capacities_ah=(capacity, capacity, capacity),
            r0_scale=r0_scale,
        )
        gate = ProtectionGate.from_stage5_config(port.cell_ids)
        gate.arm(0.0)
        simulation = simulate_discharge(
            port, gate, power_map, duration_s=args.max_duration_s, dt_s=args.dt_s
        )
        summary = runtime_summary(simulation)
        summary.update({"scenario": name, "capacity_ah": capacity, "r0_scale": r0_scale,
                        "termination_detail": simulation["termination_detail"]})
        if name == "soh_100":
            reference_runtime = summary["runtime_s"]
        records.append(summary)
        write_json(directory / f"{name}.json", simulation)

    for item in records:
        if reference_runtime:
            item["runtime_change_percent"] = (
                (item["runtime_s"] - reference_runtime) / reference_runtime * 100.0
            )

    checks = [
        judge("runtime_monotonic_with_soh",
              float(all(
                  records[index]["runtime_s"] >= records[index + 1]["runtime_s"] - 1e-6
                  for index in range(len(records) - 1)
              )), minimum=1.0, unit="bool"),
    ]
    case = compile_case_result(
        case_id="SYS017/SYS018", name="capacity_and_resistance_aging",
        model_type="verified_power_map_ecm", run_id=run_id, checks=checks,
        simulation_status="COMPLETED",
    )
    payload = {
        "run_id": run_id,
        "power_map_source": str(map_file),
        "load_current_a": args.load_a,
        "scenarios": records,
        "status": case["status"],
        "case_status": case["status"],
        "checks": case["checks"],
        "note": "老化情景是参数敏感性分析，不是实测寿命数据；单节一致性未建模",
    }
    write_json(directory / "case_result.json", payload)
    if args.json_out:
        write_json(args.json_out, payload)
    print(json.dumps({
        "run_id": run_id,
        "status": case["status"],
        "runtimes_h": {item["scenario"]: round(item["runtime_s"] / 3600, 3) for item in records},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

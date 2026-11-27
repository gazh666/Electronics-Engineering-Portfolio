"""任务 14/15：SOC × 负载 × 不一致性的长期放电测试。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.system_runtime import inconsistency_metrics, runtime_summary  # noqa: E402
from integration.battery_port_adapter import build_battery_port, load_system_config  # noqa: E402
from integration.protection_adapter import ProtectionGate  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, new_run_dir, write_json  # noqa: E402
from system_models.converter_power_map import load_power_map_csv  # noqa: E402
from system_models.long_duration_system import simulate_discharge  # noqa: E402
from validation.system_result_judge import compile_case_result, judge  # noqa: E402


def latest_power_map_file() -> Path | None:
    base = Path(__file__).resolve().parents[1] / "results" / "converter_power_map"
    candidates = sorted(base.glob("*/converter_power_map_*.csv"), key=lambda item: item.stat().st_mtime)
    return candidates[-1] if candidates else None


def load_maps(directory: Path) -> dict[float, object]:
    maps: dict[float, object] = {}
    for path in sorted(directory.glob("converter_power_map_*.csv")):
        for load, power_map in load_power_map_csv(path).items():
            maps[load] = power_map
    return maps


def main() -> int:
    parser = argparse.ArgumentParser(description="长期放电测试")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--dt-s", type=float, default=5.0)
    parser.add_argument("--max-duration-s", type=float, default=8 * 3600.0)
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir))
        if args.run_dir
        else new_run_dir(STAGE9_RESULTS / "system_lifetime", "discharge")
    )
    directory.mkdir(parents=True, exist_ok=True)
    config = load_system_config()

    map_file = latest_power_map_file()
    if map_file is None:
        summary = {
            "run_id": run_id,
            "status": "BLOCKED",
            "reason": "没有可用的真实功率映射 CSV；先运行 scripts.generate_converter_power_map",
        }
        write_json(directory / "case_result.json", summary)
        if args.json_out:
            write_json(args.json_out, summary)
        print(json.dumps({"run_id": run_id, "status": "BLOCKED"}, ensure_ascii=False))
        return 1

    maps = load_maps(map_file.parent)
    if not maps:
        summary = {"run_id": run_id, "status": "BLOCKED", "reason": f"{map_file} 中没有有效映射点"}
        write_json(directory / "case_result.json", summary)
        if args.json_out:
            write_json(args.json_out, summary)
        print(json.dumps({"run_id": run_id, "status": "BLOCKED"}, ensure_ascii=False))
        return 1

    nominal_loads = sorted(maps)

    results = []
    soc_values = (0.2, 0.4, 0.6, 0.8)
    for load in nominal_loads:
        for soc in soc_values:
            port = build_battery_port(initial_soc=(soc, soc, soc))
            gate = ProtectionGate.from_stage5_config(port.cell_ids)
            gate.arm(0.0)
            simulation = simulate_discharge(
                port, gate, maps[load],
                duration_s=args.max_duration_s,
                dt_s=args.dt_s,
            )
            summary = runtime_summary(simulation)
            summary.update({
                "load_current_a": load,
                "initial_soc": soc,
                "soc_outside_identified_window": simulation["soc_window_warning"],
                "termination_detail": simulation["termination_detail"],
            })
            results.append(summary)
            write_json(directory / f"discharge_{load:.2f}A_soc{soc:.2f}.json", simulation)

    # 不一致性：容量与初始 SOC 同时不一致
    inconsistent_port = build_battery_port(
        initial_soc=(0.40, 0.30, 0.20),
        capacities_ah=(2.0280827046460144, 1.9, 1.8),
    )
    gate = ProtectionGate.from_stage5_config(inconsistent_port.cell_ids)
    gate.arm(0.0)
    inconsistent = simulate_discharge(
        inconsistent_port, gate, maps[nominal_loads[len(nominal_loads) // 2]],
        duration_s=args.max_duration_s, dt_s=args.dt_s,
    )
    inconsistent_summary = runtime_summary(inconsistent)
    inconsistent_summary.update({
        "load_current_a": nominal_loads[len(nominal_loads) // 2],
        "case": "cell_soc_and_capacity_mismatch",
        "metrics": inconsistency_metrics(inconsistent["final_socs"], list(inconsistent_port.capacity_ah())),
    })
    write_json(directory / "discharge_inconsistent.json", inconsistent)

    valid_results = [item for item in results if not item["soc_outside_identified_window"]]
    solver_errors = {"ERROR", "MULTIPLE_OPERATING_POINTS", "NON_UNIQUE_OPERATING_POINT",
                     "CONVERTER_INPUT_OUT_OF_RANGE"}
    termination_counts: dict[str, int] = {}
    for item in results:
        termination_counts[item["status"]] = termination_counts.get(item["status"], 0) + 1
    checks = [
        judge("verified_case_count", float(len(valid_results)), minimum=1.0, unit="count"),
        judge("runtime_positive_case_count",
              float(sum(1 for item in results if item["runtime_s"] > 0.0)), minimum=1.0, unit="count"),
        judge("solver_error_count",
              float(sum(1 for item in results if item["status"] in solver_errors)),
              maximum=0.0, unit="count"),
        judge("protection_trip_count",
              float(sum(1 for item in results if item["status"] == "PROTECTION_TRIPPED")),
              maximum=0.0, unit="count"),
    ]
    case = compile_case_result(
        case_id="SYS011-SYS018",
        name="soc_load_inconsistency_matrix",
        model_type="verified_power_map_ecm",
        run_id=run_id,
        checks=checks,
        simulation_status="COMPLETED",
    )
    payload = {
        "run_id": run_id,
        "power_map_source": str(map_file),
        "loads": nominal_loads,
        "results": results,
        "termination_counts": termination_counts,
        "domain_exit_count": termination_counts.get("OUT_OF_VERIFIED_DOMAIN", 0),
        "inconsistent_case": inconsistent_summary,
        "status": case["status"],
        "case_status": case["status"],
        "checks": case["checks"],
        "model_limitations": [
            "长期模型：3S ECM + 已验证静态功率映射",
            "1 s 级步长不能证明微秒级保护响应",
            "SOC 0.6/0.8 超出第三阶段辨识区间，结果标记为外推",
            "映射有效域下限（9.0–9.6 V，取决于负载）截断深度放电，"
            "OUT_OF_VERIFIED_DOMAIN 表示拒绝外推而非计算失败",
        ],
    }
    write_json(directory / "case_result.json", payload)
    if args.json_out:
        write_json(args.json_out, payload)
    print(json.dumps({
        "run_id": run_id,
        "status": case["status"],
        "cases": len(results),
        "valid": len(valid_results),
        "runtime_hours": {f"{item['load_current_a']}A@{item['initial_soc']}": round(item["runtime_s"] / 3600, 3)
                          for item in results},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

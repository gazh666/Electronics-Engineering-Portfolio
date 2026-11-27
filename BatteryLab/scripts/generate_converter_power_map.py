"""任务 8：用真实 PowerLab 开关级闭环仿真生成 Buck 输入功率映射。

矩阵点全部来自 kaifa_power 环境中的实际 ngspice 求解；失败、未达稳态、DCM
或输出未稳压的点一律不进入映射。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from battery_models.parameters import PROJECT_ROOT, load_yaml  # noqa: E402
from integration.powerlab_adapter import load_powerlab_parameters, run_powerlab_power_map  # noqa: E402
from system_models.converter_power_map import (  # noqa: E402
    ConverterPowerMap,
    build_points,
    load_power_maps_from_payload,
)
from scripts.stage9_common import new_run_dir, write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="生成真实转换器功率映射")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--end-time-s", type=float, default=0.010)
    parser.add_argument("--step-time-s", type=float, default=5e-8)
    args = parser.parse_args()

    config = load_yaml(PROJECT_ROOT / "configs" / "converter_power_map.yaml")
    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir)) if args.run_dir
        else new_run_dir(PROJECT_ROOT / "results" / "converter_power_map", "power_map")
    )
    directory.mkdir(parents=True, exist_ok=True)

    request = {
        "mode": "power_map",
        "input_voltages_v": config["inputs_voltage_v"],
        "load_currents_a": config["load_currents_a"],
        "target_output_voltage_v": config["power_stage"]["target_output_voltage_v"],
        "end_time_s": args.end_time_s,
        "step_time_s": args.step_time_s,
        "steady_window_fraction": 0.35,
    }
    request_path = directory / "power_map_request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")

    powerlab_root = PROJECT_ROOT.parent / "PowerLab"
    bridge_result = run_powerlab_power_map(
        powerlab_root,
        request_path=request_path,
        output_path=directory / "raw_powerlab_output.json",
        timeout_s=2400,
    )
    payload = bridge_result.get("payload") or {}
    execution = bridge_result["execution"]
    if not payload:
        summary = {
            "run_id": run_id,
            "status": "SOLVER_OR_BRIDGE_FAILED",
            "execution": execution,
        }
        write_json(directory / "power_map_validation.json", summary)
        if args.json_out:
            write_json(args.json_out, summary)
        print(json.dumps({"run_id": run_id, "status": summary["status"]}, ensure_ascii=False))
        return 1

    controller = load_powerlab_parameters(powerlab_root)["controller"]
    points = build_points(payload, controller)
    maps = load_power_maps_from_payload(payload, controller)

    per_load = {}
    for load, power_map in sorted(maps.items()):
        csv_path = directory / f"converter_power_map_{load:.2f}A.csv"
        power_map.to_csv(csv_path)
        per_load[f"{load:.2f}"] = {
            "status": "VALID",
            "verified_voltage_range_v": [power_map.minimum_verified_voltage_v, power_map.maximum_verified_voltage_v],
            "point_count": len(power_map.points),
            "csv": csv_path.name,
            "minimum_efficiency_percent": min(
                item.efficiency_percent for item in power_map.points if item.efficiency_percent is not None
            ),
        }

    rejected = [
        {
            "input_voltage_v": item["input_voltage_v"],
            "load_current_a": item["load_current_a"],
            "status": item["status"],
            "steady_state": item.get("steady_state"),
            "ccm": item.get("ccm"),
            "error": item.get("error"),
        }
        for item in payload.get("points", [])
        if item.get("status") != "CONVERGED" or not item.get("ccm")
    ]
    dcm_loads = sorted({
        item["load_current_a"] for item in payload.get("points", [])
        if item.get("status") == "CONVERGED" and item.get("ccm") is False
    })

    statuses = [item.get("status") for item in payload.get("points", [])]
    converged = statuses.count("CONVERGED")
    summary = {
        "run_id": run_id,
        "status": "PASS" if converged == len(statuses) and not rejected else "PARTIAL",
        "bridge": {
            "duration_s": execution.get("duration_s"),
            "returncode": execution.get("returncode"),
            "status": execution.get("status"),
        },
        "point_count": len(statuses),
        "converged_count": converged,
        "rejected_count": len(rejected),
        "dcm_loads_a": dcm_loads,
        "valid_maps": per_load,
        "rejected_points": rejected,
        "request": request,
        "source": "powerlab_real_switch_level_spice",
        "model_limitations": [
            "PowerLab 教学 NMOS Level 1 / 非理想二极管，不是商业器件模型",
            "映射只覆盖 9.0–12.6 V 与已收敛 CCM 负载点，禁止外推",
        ],
    }
    write_json(directory / "power_map_validation.json", summary)
    write_json(directory / "converter_power_map_summary.json", summary)
    if args.json_out:
        write_json(args.json_out, summary)
    print(json.dumps({
        "run_id": run_id,
        "status": summary["status"],
        "converged": converged,
        "rejected": len(rejected),
        "valid_maps": list(per_load),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

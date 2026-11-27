"""任务 16/17/18：保护联动与故障注入。

分两部分，避免混淆：

- **联合 SPICE**：在真实网表中把保护开关控制信号置 0，观察电池电流抑制与
  输出电压衰减；这证明"关断后的电气后果"，不证明 BMS 检测时间。
- **行为级注入**：直接驱动第五阶段真实 ProtectionController，验证许可、锁存
  与复位逻辑。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from circuits.integrated_protection import extract_protection_timing  # noqa: E402
from integration.battery_port_adapter import build_battery_port  # noqa: E402
from integration.measurement_exchange import SystemMeasurement, build_bundle, save_bundle  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, new_run_dir, validation_limits, write_json  # noqa: E402
from simulations.system_spice_runner import load_waveform, run_integrated_case  # noqa: E402
from validation.system_fault_injection import run_fault_scenarios  # noqa: E402
from validation.system_result_judge import CheckResult, compile_case_result, judge, judge_boolean  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="保护联动与故障注入")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--end-time-s", type=float, default=0.014)
    parser.add_argument("--fault-time-s", type=float, default=0.012)
    parser.add_argument("--spice", action="store_true", help="同时执行联合 SPICE 保护工况")
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir))
        if args.run_dir
        else new_run_dir(STAGE9_RESULTS / "system_protection", "protection")
    )
    directory.mkdir(parents=True, exist_ok=True)
    limits = validation_limits()

    behavioral = run_fault_scenarios()
    write_json(directory / "fault_injection.json", behavioral)

    checks = []
    for record in behavioral["records"]:
        for item in record.get("checks", []):
            checks.append(CheckResult(
                metric=f"{record['scenario']}.{item['metric']}",
                status=item["status"],
                actual=float(item["actual"]) if isinstance(item["actual"], (int, float, bool)) else None,
                minimum=None, maximum=None, unit="bool", reason=None,
            ))
    checks.append(judge("fault_injection_pass_ratio",
                        behavioral["pass_count"] / max(behavioral["scenario_count"], 1) * 100.0,
                        minimum=100.0, unit="%"))

    payload: dict = {
        "run_id": run_id,
        "behavioral": behavioral,
        "spice": None,
        "protection_is_stage5_engineering_config": True,
        "thresholds_are_bq76922_registers": False,
    }

    if args.spice:
        port = build_battery_port()
        result = run_integrated_case(
            port,
            name="SYS025_protection_fault",
            run_directory=directory,
            end_time_s=args.end_time_s,
            step_time_s=2.5e-8,
            fault_time_s=args.fault_time_s,
            timeout_s=1800,
        )
        integrated = result.get("integrated") or {}
        payload["spice"] = integrated
        waveform_path = directory / "waveform.csv"
        if integrated.get("status") == "CONVERGED" and waveform_path.is_file():
            waveform = load_waveform(waveform_path)
            timing = extract_protection_timing(
                time_s=waveform["time_s"],
                battery_current_a=waveform["battery_current_a"],
                battery_voltage_v=waveform["battery_voltage_v"],
                converter_input_voltage_v=waveform["converter_input_voltage_v"],
                output_voltage_v=waveform["output_voltage_v"],
                fault_start_time_s=args.fault_time_s,
                control_off_time_s=args.fault_time_s + 1e-5,
                current_ratio=limits["protection"]["current_suppression_ratio"]["max"],
                converter_input_min_v=limits["system"]["minimum_converter_input_voltage_v"],
                output_voltage_min_v=limits["protection"]["output_decay_voltage_v"]["max"],
            )
            suppression_ratio = None
            if timing["battery_current_suppressed_time_s"] is not None:
                suppressed_index = int(np.searchsorted(waveform["time_s"], timing["battery_current_suppressed_time_s"]))
                if suppressed_index < len(waveform["battery_current_a"]):
                    suppression_ratio = abs(waveform["battery_current_a"][suppressed_index]) / max(
                        abs(timing["pre_fault_battery_current_a"]), 1e-12
                    )
            payload["spice_protection_timing"] = timing
            payload["suppression_ratio"] = suppression_ratio
            checks.append(judge("current_suppression_ratio", suppression_ratio,
                                maximum=limits["protection"]["current_suppression_ratio"]["max"], unit="ratio"))
            checks.append(judge_boolean("discharge_disabled_after_gate_off",
                                        timing["battery_current_suppressed_time_s"] is not None))
            checks.append(judge("output_hold_time_s", timing["output_hold_time_s"], minimum=0.0, unit="s"))
        else:
            checks.append(CheckResult(metric="spice_protection_case", status="NOT_VERIFIED",
                                      actual=None, minimum=None, maximum=None, unit=None,
                                      reason=integrated.get("error") or "SPICE case not converged"))

    case = compile_case_result(
        case_id="SYS003/SYS019/SYS020/SYS021/SYS022/SYS023/SYS024/SYS025",
        name="protection_and_fault_injection",
        model_type="behavioral_protection_simulation",
        run_id=run_id,
        checks=checks,
        simulation_status="COMPLETED" if not args.spice else str((payload["spice"] or {}).get("status")),
    )
    payload.update({"status": case["status"],
                    "checks": [item.to_dict() for item in checks],
                    "case_status": case["status"]})
    write_json(directory / "case_result.json", payload)

    save_bundle(
        build_bundle(
            run_id=run_id,
            source="behavioral_protection_simulation",
            measurements=[
                SystemMeasurement("fault_injection_pass_count", float(behavioral["pass_count"]), "count",
                                  "behavioral_protection_simulation", run_id,
                                  str(directory / "fault_injection.json"), "VERIFIED", "SYS023"),
                SystemMeasurement(
                    "spice_current_suppression_ratio",
                    payload.get("suppression_ratio"), "ratio",
                    "behavioral_protection_simulation", run_id,
                    str(directory / "case_result.json"),
                    "VERIFIED" if payload.get("suppression_ratio") is not None else "NOT_VERIFIED",
                    "SYS025",
                ),
            ],
            case_id="SYS025",
            model_type="behavioral_protection_simulation",
            power_boundary="battery_terminal_to_load",
        ),
        directory / "system_measurements.json",
    )
    if args.json_out:
        write_json(args.json_out, payload)
    print(__import__("json").dumps({
        "run_id": run_id,
        "status": case["status"],
        "behavioral": {"pass": behavioral["pass_count"], "total": behavioral["scenario_count"]},
        "spice_suppression_ratio": payload.get("suppression_ratio"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

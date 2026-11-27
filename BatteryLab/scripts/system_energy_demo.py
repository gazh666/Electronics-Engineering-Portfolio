"""任务 22：能量守恒与损耗分解（基于真实 SPICE 波形）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.system_loss_breakdown import breakdown_from_waveform  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, new_run_dir, validation_limits, write_json  # noqa: E402
from simulations.system_spice_runner import load_waveform  # noqa: E402
from validation.system_energy_validator import validate_energy  # noqa: E402
from validation.system_result_judge import compile_case_result, judge  # noqa: E402


def latest_waveform() -> Path | None:
    base = Path(__file__).resolve().parents[1] / "results" / "system_spice"
    candidates = sorted(base.glob("*/waveform.csv"), key=lambda item: item.stat().st_mtime)
    return candidates[-1] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description="能量守恒与损耗分解")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--waveform", default=None)
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir))
        if args.run_dir
        else new_run_dir(STAGE9_RESULTS / "system_energy", "energy")
    )
    directory.mkdir(parents=True, exist_ok=True)
    limits = validation_limits()

    waveform_path = Path(args.waveform) if args.waveform else latest_waveform()
    if waveform_path is None or not waveform_path.is_file():
        payload = {
            "run_id": run_id,
            "status": "BLOCKED",
            "reason": "没有联合 SPICE 波形；先运行 scripts.integrated_buck_demo",
        }
        write_json(directory / "case_result.json", payload)
        if args.json_out:
            write_json(args.json_out, payload)
        print(json.dumps({"run_id": run_id, "status": "BLOCKED"}, ensure_ascii=False))
        return 1

    waveform = load_waveform(waveform_path)
    end_time = waveform["time_s"][-1]
    steady_start = end_time * 0.7
    energy = validate_energy(
        time_s=waveform["time_s"],
        battery_voltage_v=waveform["battery_voltage_v"],
        battery_current_a=waveform["battery_current_a"],
        converter_input_voltage_v=waveform["converter_input_voltage_v"],
        converter_input_current_a=waveform["converter_input_current_a"],
        output_voltage_v=waveform["output_voltage_v"],
        load_current_a=waveform["load_current_a"],
        path_resistance_ohm=0.052,
        steady_window_start_s=steady_start,
        residual_limit_percent=limits["energy"]["steady_state_residual_percent"]["max"],
    )
    breakdown = breakdown_from_waveform(
        waveform,
        path_resistance_ohm=0.052,
        battery_internal_resistance_ohm=3 * 0.0770684639742517,
        steady_window_start_s=steady_start,
    )
    checks = [
        judge("boundary_a_residual_percent", energy["boundary_a_residual_percent"],
              maximum=limits["energy"]["steady_state_residual_percent"]["max"], unit="%"),
        judge("converter_efficiency_percent", energy["converter_efficiency_percent"],
              minimum=0.0, maximum=100.0, unit="%"),
    ]
    case = compile_case_result(
        case_id="SYS028", name="power_and_energy_conservation",
        model_type="spice_coupled_simulation", run_id=run_id, checks=checks,
        simulation_status="COMPLETED",
    )
    payload = {
        "run_id": run_id,
        "waveform": str(waveform_path),
        "energy": energy,
        "loss_breakdown": breakdown,
        "status": case["status"],
        "case_status": case["status"],
        "checks": case["checks"],
        "limitations": [
            "Buck 损耗为输入输出差，不能分离导通/开关分量",
            "电池内部损耗按辨识 R0 估算，未包含极化损耗的独立积分",
        ],
    }
    write_json(directory / "case_result.json", payload)
    if args.json_out:
        write_json(args.json_out, payload)
    print(json.dumps({
        "run_id": run_id, "status": case["status"],
        "residual_percent": energy["boundary_a_residual_percent"],
        "efficiency_percent": energy["converter_efficiency_percent"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

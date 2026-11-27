"""任务 10：同一网表联合仿真（电池 ECM + 保护通路 + PowerLab Buck 闭环）。

真实开关级求解在 kaifa_power 环境完成；本脚本负责判定、能量校验与归档。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from analysis.system_power_metrics import power_budget  # noqa: E402
from integration.battery_port_adapter import build_battery_port, cell_ecm_parameters  # noqa: E402
from integration.measurement_exchange import SystemMeasurement, build_bundle, save_bundle  # noqa: E402
from scripts.stage9_common import validation_limits, write_json  # noqa: E402
from simulations.system_spice_runner import load_waveform, new_run_directory, run_integrated_case  # noqa: E402
from validation.system_energy_validator import validate_energy  # noqa: E402
from validation.system_result_judge import compile_case_result, judge  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="联合 SPICE 标称工况")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--end-time-s", type=float, default=0.012)
    parser.add_argument("--step-time-s", type=float, default=2.5e-8)
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir)) if args.run_dir else new_run_directory("integrated_nominal")
    )
    directory.mkdir(parents=True, exist_ok=True)
    limits = validation_limits()
    port = build_battery_port()
    port_state = port.get_port_state()

    result = run_integrated_case(
        port,
        name="SYS001_nominal_discharge",
        run_directory=directory,
        end_time_s=args.end_time_s,
        step_time_s=args.step_time_s,
        timeout_s=1800,
    )
    integrated = result.get("integrated") or {}
    status = integrated.get("status")

    checks = []
    payload: dict = {
        "run_id": run_id,
        "case_id": "SYS001",
        "status": None,
        "simulation_status": status,
        "integrated": integrated,
        "battery_port_state": {
            "effective_voltage_v": port_state.effective_voltage_v,
            "total_series_resistance_ohm": port_state.total_series_resistance_ohm,
            "socs": list(port_state.socs),
            "inside_identified_window": port_state.inside_identified_window,
        },
        "bridge": result["bridge_execution"],
    }

    if status != "CONVERGED":
        payload["error"] = integrated.get("error") or result["bridge_execution"].get("stderr_tail")
        payload["checks"] = checks
        payload["case_status"] = "ERROR"
        write_json(directory / "case_result.json", payload)
        if args.json_out:
            write_json(args.json_out, payload)
        print(json.dumps({"run_id": run_id, "status": "ERROR"}, ensure_ascii=False))
        return 1

    metrics = integrated["metrics"]
    nominal = limits["nominal"]
    checks.append(judge("output_voltage_mean_v", metrics["output_voltage_mean_v"],
                        minimum=nominal["output_voltage_mean_v"]["min"],
                        maximum=nominal["output_voltage_mean_v"]["max"], unit="V"))
    steady_error = abs(metrics["output_voltage_mean_v"] - 5.0)
    checks.append(judge("steady_state_error_v", steady_error,
                        maximum=nominal["steady_state_error_v"]["max"], unit="V"))
    checks.append(judge("output_voltage_ripple_vpp", metrics["output_voltage_ripple_vpp"],
                        maximum=nominal["output_ripple_vpp"]["max"], unit="V"))
    checks.append(judge("inductor_peak_current_a", metrics["inductor_peak_current_a"],
                        maximum=nominal["inductor_peak_current_a"]["max"], unit="A"))
    checks.append(judge("converter_input_voltage_v", metrics["input_voltage_mean_v"],
                        minimum=nominal["converter_input_voltage_v"]["min"],
                        maximum=nominal["converter_input_voltage_v"]["max"], unit="V"))

    waveform_path = directory / "waveform.csv"
    energy = None
    budget = None
    if waveform_path.is_file():
        waveform = load_waveform(waveform_path)
        steady_start = waveform["time_s"][-1] * 0.7
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
        checks.append(judge("energy_boundary_a_residual_percent", energy["boundary_a_residual_percent"],
                            maximum=limits["energy"]["steady_state_residual_percent"]["max"], unit="%"))
        mask = np.asarray(waveform["time_s"]) >= steady_start
        budget = power_budget(
            battery_voltage_v=waveform["battery_voltage_v"],
            battery_current_a=waveform["battery_current_a"],
            converter_input_voltage_v=waveform["converter_input_voltage_v"],
            converter_input_current_a=waveform["converter_input_current_a"],
            output_voltage_v=waveform["output_voltage_v"],
            load_current_a=waveform["load_current_a"],
            path_resistance_ohm=0.052,
            steady_mask=mask,
        )
        checks.append(judge("power_boundary_residual_percent", budget["boundary_residual_percent"],
                            maximum=limits["energy"]["steady_state_residual_percent"]["max"], unit="%"))

        # 双向耦合证据：电池端电压必须随负载电流变化（不是理想固定源）
        ibat = np.asarray(waveform["battery_current_a"], dtype=float)[mask]
        vbat = np.asarray(waveform["battery_voltage_v"], dtype=float)[mask]
        open_circuit = sum(cell["ocv_v"] for cell in cell_ecm_parameters(port))
        drop = open_circuit - float(np.mean(vbat))
        correlation = float(np.corrcoef(ibat, vbat)[0, 1]) if ibat.size > 10 and ibat.std() > 0 else None
        payload["bidirectional_coupling"] = {
            "open_circuit_voltage_v": open_circuit,
            "battery_voltage_mean_v": float(np.mean(vbat)),
            "load_induced_voltage_drop_v": drop,
            "current_voltage_correlation": correlation,
            "verdict": "BATTERY_VOLTAGE_DEPENDS_ON_LOAD" if drop > 1e-3 else "NOT_DEMONSTRATED",
        }

    case = compile_case_result(
        case_id="SYS001",
        name="nominal_discharge",
        model_type="spice_coupled_simulation",
        run_id=run_id,
        checks=checks,
        simulation_status=status,
    )
    payload.update({
        "status": case["status"],
        "case_status": case["status"],
        "checks": case["checks"],
        "metrics": metrics,
        "energy": energy,
        "power_budget": budget,
    })
    write_json(directory / "case_result.json", payload)

    measurements = [
        SystemMeasurement("output_voltage_mean_v", metrics["output_voltage_mean_v"], "V", "spice_coupled_simulation",
                          run_id, str(directory / "waveform.csv"), "VERIFIED", "SYS001"),
        SystemMeasurement("output_voltage_ripple_vpp", metrics["output_voltage_ripple_vpp"], "V", "spice_coupled_simulation",
                          run_id, str(directory / "waveform.csv"), "VERIFIED", "SYS001"),
        SystemMeasurement("inductor_peak_current_a", metrics["inductor_peak_current_a"], "A", "spice_coupled_simulation",
                          run_id, str(directory / "waveform.csv"), "VERIFIED", "SYS001"),
        SystemMeasurement("efficiency_percent", metrics.get("efficiency_percent"), "%", "spice_coupled_simulation",
                          run_id, str(directory / "waveform.csv"), "VERIFIED", "SYS001"),
    ]
    bundle = build_bundle(
        run_id=run_id,
        source="spice_coupled_simulation",
        measurements=measurements,
        case_id="SYS001",
        model_type="spice_coupled_simulation",
        battery_parameter_source="stage3_identified_first_order_rc_ecm",
        converter_configuration={"topology": "buck", "controller": "powerlab_pi", "power_stage": "powerlab_SW_MODEL"},
        time_window={"start_s": 0.0, "end_s": args.end_time_s},
        power_boundary="battery_terminal_to_load",
        code_hash=integrated.get("netlist_sha256"),
    )
    save_bundle(bundle, directory / "system_measurements.json")

    if args.json_out:
        write_json(args.json_out, payload)
    print(json.dumps({"run_id": run_id, "status": case["status"],
                      "vout": metrics["output_voltage_mean_v"],
                      "ripple": metrics["output_voltage_ripple_vpp"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

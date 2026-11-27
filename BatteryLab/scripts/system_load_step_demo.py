"""任务 12：平均模型双向动态耦合的负载阶跃与稳态建立时间。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from analysis.system_power_metrics import power_budget  # noqa: E402
from analysis.system_transient_metrics import find_settling_time, step_metrics  # noqa: E402
from integration.battery_port_adapter import build_battery_port, load_system_config  # noqa: E402
from integration.measurement_exchange import SystemMeasurement, build_bundle, save_bundle  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, new_run_dir, validation_limits, write_json  # noqa: E402
from simulations.system_average_runner import run_average_case  # noqa: E402
from validation.system_result_judge import compile_case_result, judge  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="负载阶跃平均模型")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--duration-s", type=float, default=0.04)
    parser.add_argument("--dt-s", type=float, default=2e-6)
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir))
        if args.run_dir
        else new_run_dir(STAGE9_RESULTS / "system_average", "load_step")
    )
    directory.mkdir(parents=True, exist_ok=True)
    limits = validation_limits()
    port = build_battery_port()
    config = load_system_config()

    step_time = 0.020
    load_profile = ((0.0, 2.5), (step_time, 5.0), (0.030, 2.5))
    result = run_average_case(
        port,
        config,
        name="SYS002_load_step",
        run_directory=directory,
        duration_s=args.duration_s,
        dt_s=args.dt_s,
        load_profile=load_profile,
    )
    records = result["records"]
    time_s = np.array([row["time_s"] for row in records], dtype=float)
    vout = np.array([row["output_voltage_v"] for row in records], dtype=float)
    ibat = np.array([row["battery_current_a"] for row in records], dtype=float)
    il = np.array([row["inductor_current_a"] for row in records], dtype=float)
    iout = np.array([row["load_current_a"] for row in records], dtype=float)
    vin = np.array([row["input_voltage_v"] for row in records], dtype=float)
    steady = time_s >= 0.035
    battery_voltage = vin + ibat * 0.052
    budget = power_budget(
        battery_voltage_v=battery_voltage, battery_current_a=ibat,
        converter_input_voltage_v=vin, converter_input_current_a=ibat,
        output_voltage_v=vout, load_current_a=iout,
        path_resistance_ohm=0.052, steady_mask=steady,
    )

    step_down = step_metrics(time_s, vout, step_time_s=step_time, post_window_s=0.008, nominal_v=5.0)
    settling = find_settling_time(
        time_s[time_s >= step_time], vout[time_s >= step_time], 5.0,
        limits["dynamic"]["settling_tolerance_v"],
        hold_time_s=limits["dynamic"]["settling_hold_s"],
    )
    dynamic = limits["dynamic"]
    checks = [
        judge("load_step_deviation_v", step_down.get("deviation_v"),
              maximum=dynamic["load_step_deviation_v"]["max"], unit="V"),
        judge("settling_time_s", None if settling is None else settling - step_time,
              maximum=0.005, unit="s"),
        judge("output_voltage_steady_v", float(np.mean(vout[steady])), minimum=4.9, maximum=5.1, unit="V"),
        judge("inductor_peak_current_a", float(np.max(il)), maximum=3.5, unit="A"),
    ]
    case = compile_case_result(
        case_id="SYS002", name="load_step_1a_to_2a",
        model_type="averaged_dynamic_coupled_simulation",
        run_id=run_id, checks=checks, simulation_status="COMPLETED",
    )
    payload = {
        "run_id": run_id,
        "case_id": "SYS002",
        "status": case["status"],
        "model_type": "averaged_dynamic_coupled_simulation",
        "checks": case["checks"],
        "step_metrics": step_down,
        "settling_time_s": settling,
        "settling_time_after_step_s": None if settling is None else settling - step_time,
        "power_budget": budget,
        "battery_voltage_droop_v": float(np.max(vin[time_s <= step_time]) - np.min(vin)),
        "battery_power_follows_load": float(np.corrcoef(ibat[~steady], vin[~steady])[0, 1]),
        "limitations": result["limitations"],
        "hardware_validated": False,
    }
    write_json(directory / "case_result.json", payload)
    save_bundle(
        build_bundle(
            run_id=run_id, source="averaged_dynamic_coupled_simulation",
            measurements=[
                SystemMeasurement("load_step_deviation_v", step_down.get("deviation_v"), "V",
                                  "averaged_dynamic_coupled_simulation", run_id,
                                  str(directory / "average_result.json"), "VERIFIED", "SYS002"),
                SystemMeasurement("settling_time_s", None if settling is None else settling - step_time, "s",
                                  "averaged_dynamic_coupled_simulation", run_id,
                                  str(directory / "average_result.json"),
                                  "VERIFIED" if settling else "NOT_VERIFIED", "SYS002"),
            ],
            case_id="SYS002", model_type="averaged_dynamic_coupled_simulation",
            battery_parameter_source="stage3_identified_first_order_rc_ecm",
            converter_configuration={"topology": "buck_averaged_ccm", "controller": "powerlab_pi"},
            time_window={"start_s": 0.0, "end_s": args.duration_s},
            power_boundary="battery_terminal_to_load",
        ),
        directory / "system_measurements.json",
    )
    if args.json_out:
        write_json(args.json_out, payload)
    print(__import__("json").dumps({
        "run_id": run_id, "status": case["status"],
        "deviation_v": step_down.get("deviation_v"),
        "settling_after_step_s": payload["settling_time_after_step_s"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

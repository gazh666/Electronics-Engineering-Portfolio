"""平均模型双向动态运行器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from integration.battery_port_adapter import BatteryPort
from system_models.averaged_system import AveragedSystemParams, simulate_averaged_system
from system_models.system_controller import PIController


def params_from_port(port: BatteryPort, config: dict[str, Any], *, capacitance_f: float | None = None) -> AveragedSystemParams:
    converter = config["discharge_converter"]
    baseline = converter["baseline"]
    return AveragedSystemParams(
        input_capacitance_f=100e-6,
        output_capacitance_f=float(capacitance_f or baseline["capacitance_f"]),
        inductance_h=float(baseline["inductance_h"]),
        battery_resistance_ohm=sum(cell.r0_ohm for cell in port.cell_parameters()),
        path_resistance_ohm=float(config["protection"]["path_resistance_ohm"]),
        inductor_dcr_ohm=float(baseline["inductor_dcr_ohm"]),
        mosfet_rds_on_ohm=0.020,
        diode_drop_v=0.35,
    ).validate()


def run_average_case(
    port: BatteryPort,
    config: dict[str, Any],
    *,
    name: str,
    run_directory: str | Path,
    duration_s: float = 0.02,
    dt_s: float = 2e-6,
    load_profile: Sequence[tuple[float, float]] = ((0.0, 2.5),),
    protection_disconnect_time_s: float | None = None,
    capacitance_f: float | None = None,
) -> dict[str, Any]:
    directory = Path(run_directory)
    directory.mkdir(parents=True, exist_ok=True)
    params = params_from_port(port, config, capacitance_f=capacitance_f)
    controller_config = config["discharge_converter"]["controller"]
    controller = PIController(
        kp=float(controller_config["kp"]),
        ki=float(controller_config["ki"]),
        duty_min=float(controller_config["duty_min"]),
        duty_max=float(controller_config["duty_max"]),
    )
    port_state = port.get_port_state()
    result = simulate_averaged_system(
        params,
        effective_battery_voltage_v=port_state.effective_voltage_v,
        target_output_voltage_v=float(config["discharge_converter"]["output_voltage_target_v"]),
        duration_s=duration_s,
        dt_s=dt_s,
        soft_start_s=float(controller_config["soft_start_s"]),
        controller=controller,
        load_profile=load_profile,
        protection_disconnect_time_s=protection_disconnect_time_s,
    )
    result["case"] = name
    result["run_id"] = directory.name
    result["initial_battery_effective_voltage_v"] = port_state.effective_voltage_v
    (directory / "average_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return result


__all__ = ["params_from_port", "run_average_case"]

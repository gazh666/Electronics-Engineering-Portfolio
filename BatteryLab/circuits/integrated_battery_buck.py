"""电池 + Buck 一体化电路装配（Task 11）。

把第三阶段辨识 ECM 接入 PowerLab 验证过的功率级与闭环反馈；输入电压不再
是理想源，而是由电池电流在 ECM 上产生的真实压降。
"""

from __future__ import annotations

from typing import Any, Sequence

from circuits.system_spice_netlist import (
    IntegratedLayout,
    build_integrated_system,
    save_netlist,
)
from integration.battery_port_adapter import BatteryPort, cell_ecm_parameters
from integration.battery_port_adapter import load_system_config


def system_electrical_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = config or load_system_config()
    converter = payload["discharge_converter"]
    baseline = converter["baseline"]
    controller = converter["controller"]
    simulation = payload["simulation"]
    return {
        "path_resistance_ohm": float(payload["protection"]["path_resistance_ohm"]),
        "inductance_h": float(baseline["inductance_h"]),
        "inductor_dcr_ohm": float(baseline["inductor_dcr_ohm"]),
        "capacitance_f": float(baseline["capacitance_f"]),
        "capacitor_esr_ohm": float(baseline["capacitor_esr_ohm"]),
        "target_output_voltage_v": float(converter["output_voltage_target_v"]),
        "switching_frequency_hz": float(converter["switching_frequency_hz"]),
        "load_resistance_ohm": float(converter["output_voltage_target_v"]) / float(
            converter["rated_output_current_a"]
        ),
        "kp": float(controller["kp"]),
        "ki": float(controller["ki"]),
        "duty_min": float(controller["duty_min"]),
        "duty_max": float(controller["duty_max"]),
        "soft_start_s": float(controller["soft_start_s"]),
        "spice_end_time_s": float(simulation["spice_end_time_s"]),
    }


def build_from_port(
    port: BatteryPort,
    *,
    load_resistance_ohm: float | None = None,
    protection_control_points: Sequence[tuple[float, float]] | None = None,
    end_time_s: float | None = None,
    config: dict[str, Any] | None = None,
    inductance_h: float | None = None,
    capacitance_f: float | None = None,
    inductor_dcr_ohm: float | None = None,
    capacitor_esr_ohm: float | None = None,
    kp: float | None = None,
    ki: float | None = None,
) -> tuple[Any, IntegratedLayout, dict[str, Any]]:
    settings = system_electrical_config(config)
    cells = cell_ecm_parameters(port)
    resolved = dict(settings)
    resolved.update(
        {
            "load_resistance_ohm": settings["load_resistance_ohm"] if load_resistance_ohm is None else load_resistance_ohm,
            "inductance_h": settings["inductance_h"] if inductance_h is None else inductance_h,
            "capacitance_f": settings["capacitance_f"] if capacitance_f is None else capacitance_f,
            "inductor_dcr_ohm": settings["inductor_dcr_ohm"] if inductor_dcr_ohm is None else inductor_dcr_ohm,
            "capacitor_esr_ohm": settings["capacitor_esr_ohm"] if capacitor_esr_ohm is None else capacitor_esr_ohm,
            "kp": settings["kp"] if kp is None else kp,
            "ki": settings["ki"] if ki is None else ki,
            "end_time_s": settings["spice_end_time_s"] if end_time_s is None else end_time_s,
        }
    )
    open_circuit_v = sum(cell["ocv_v"] for cell in cells)
    circuit, layout = build_integrated_system(
        cells,
        path_resistance_ohm=resolved["path_resistance_ohm"],
        input_capacitance_f=100e-6,
        input_capacitor_ic_v=open_circuit_v - 0.3,
        inductance_h=resolved["inductance_h"],
        inductor_dcr_ohm=resolved["inductor_dcr_ohm"],
        capacitance_f=resolved["capacitance_f"],
        capacitor_esr_ohm=resolved["capacitor_esr_ohm"],
        load_resistance_ohm=resolved["load_resistance_ohm"],
        target_output_voltage_v=resolved["target_output_voltage_v"],
        switching_frequency_hz=resolved["switching_frequency_hz"],
        kp=resolved["kp"],
        ki=resolved["ki"],
        duty_min=resolved["duty_min"],
        duty_max=resolved["duty_max"],
        soft_start_s=resolved["soft_start_s"],
        protection_control_points=protection_control_points,
        end_time_s=resolved["end_time_s"],
    )
    return circuit, layout, resolved


def save_system_netlist(circuit: Any, path: str) -> str:
    return str(save_netlist(circuit, path))


__all__ = ["build_from_port", "save_system_netlist", "system_electrical_config"]

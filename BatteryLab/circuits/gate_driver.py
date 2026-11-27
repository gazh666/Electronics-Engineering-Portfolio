"""栅极驱动：解析功耗与真实 ngspice 栅极电荷瞬态。

驱动功率 ``P = Qg × Vgs × fsw`` 是开关频率的函数，与负载电流无关；峰值电流由
``Vdrv / Rg`` 决定。教学网的栅极电容按 ``Ceq = Qg / Vgs`` 等效，从而让 SPICE
的栅极波形与解析电荷一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from PySpice.Spice.Netlist import Circuit

from circuits.spice_utils import run_transient, save_netlist
from protection.limits import ProtectionLimits


class GateDriverError(ValueError):
    """栅极驱动参数非法。"""


@dataclass(frozen=True)
class GateDriveAnalysis:
    gate_charge_nc: float
    drive_voltage_v: float
    gate_resistance_ohm: float
    switching_frequency_hz: float
    equivalent_gate_capacitance_f: float
    peak_gate_current_a: float
    theoretical_rise_time_s: float
    drive_power_per_fet_w: float
    total_drive_power_w: float
    fet_count: int

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def analyze_gate_drive(limits: ProtectionLimits, fet_count: int = 2) -> GateDriveAnalysis:
    if fet_count < 1:
        raise GateDriverError("FET 数量至少为 1")
    qg = limits.gate_charge_nc * 1e-9
    vgs = limits.gate_drive_voltage_v
    rg = limits.gate_resistance_ohm
    frequency = limits.switching_frequency_hz
    capacitance = qg / vgs
    peak = vgs / rg
    rise = 2.2 * rg * capacitance
    power = qg * vgs * frequency
    return GateDriveAnalysis(
        gate_charge_nc=limits.gate_charge_nc,
        drive_voltage_v=vgs,
        gate_resistance_ohm=rg,
        switching_frequency_hz=frequency,
        equivalent_gate_capacitance_f=capacitance,
        peak_gate_current_a=peak,
        theoretical_rise_time_s=rise,
        drive_power_per_fet_w=power,
        total_drive_power_w=power * fet_count,
        fet_count=fet_count,
    )


def build_gate_driver_circuit(limits: ProtectionLimits) -> Circuit:
    circuit = Circuit("BatteryLab gate driver transient")
    capacitance = analyze_gate_drive(limits, fet_count=1).equivalent_gate_capacitance_f
    circuit.PulseVoltageSource(
        "DRV",
        "drv",
        circuit.gnd,
        initial_value=0.0,
        pulsed_value=limits.gate_drive_voltage_v,
        delay_time=1e-6,
        rise_time=1e-9,
        fall_time=1e-9,
        pulse_width=10e-6,
        period=20e-6,
    )
    circuit.R("G", "drv", "gate", limits.gate_resistance_ohm)
    circuit.C("GS", "gate", circuit.gnd, capacitance)
    circuit.R("PD", "gate", circuit.gnd, limits.gate_pulldown_ohm)
    return circuit


def run_gate_driver_spice(limits: ProtectionLimits) -> dict[str, Any]:
    circuit = build_gate_driver_circuit(limits)
    data = run_transient(
        circuit,
        duration_s=1.5e-6,
        step_s=5e-10,
        max_step_s=5e-10,
        nodes=("drv", "gate"),
        branches=("VDRV",),
        reltol=1e-6,
        abstol=1e-12,
        vntol=1e-9,
    )
    time_array = data["time_s"]
    gate = data["gate"]
    current = data["I:vdrv"]
    steady = float(np.max(gate))
    # 10%-90% 上升时间，从驱动跳变之后开始测量。
    low = 0.1 * steady
    high = 0.9 * steady
    above_low = np.where(gate >= low)[0]
    above_high = np.where(gate >= high)[0]
    rise_time: float | None = None
    if above_low.size and above_high.size and above_high[0] > above_low[0]:
        rise_time = float(time_array[above_high[0]] - time_array[above_low[0]])
    peak_current = float(np.max(np.abs(current)))
    return {
        "time_s": time_array,
        "gate_voltage_v": gate,
        "drive_current_a": current,
        "steady_gate_voltage_v": steady,
        "measured_peak_current_a": peak_current,
        "measured_rise_time_s": rise_time,
        "netlist": str(circuit),
    }


def save_gate_driver_netlist(limits: ProtectionLimits, path) -> Any:
    return save_netlist(build_gate_driver_circuit(limits), path)

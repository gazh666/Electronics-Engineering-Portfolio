"""电阻分压电路。

拓扑::

    vin ── R1 ── out ── R2 ── gnd
      │
     Vinput (DC)

理论输出：Vout = Vin × R2 / (R1 + R2)。
本模块只构建电路与给出理论值，不伪造任何仿真结果。
"""

from __future__ import annotations

import math

from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_Ohm, u_V


def _positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是数值，实际为 {value!r}")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} 必须是有限正数，实际为 {value!r}")
    return number


def build_voltage_divider(
    vin_v: float = 12.0,
    r1_ohm: float = 1_000.0,
    r2_ohm: float = 1_000.0,
    *,
    name: str = "Voltage Divider",
) -> Circuit:
    """构建电阻分压电路（12 V / 1 kΩ / 1 kΩ → 6 V）。"""
    vin_v = _positive(vin_v, "vin_v")
    r1_ohm = _positive(r1_ohm, "r1_ohm")
    r2_ohm = _positive(r2_ohm, "r2_ohm")

    circuit = Circuit(name)
    circuit.V("input", "vin", circuit.gnd, vin_v @ u_V)
    circuit.R(1, "vin", "out", r1_ohm @ u_Ohm)
    circuit.R(2, "out", circuit.gnd, r2_ohm @ u_Ohm)
    return circuit


def theoretical_output_voltage(
    vin_v: float = 12.0,
    r1_ohm: float = 1_000.0,
    r2_ohm: float = 1_000.0,
) -> float:
    """分压公式给出的理论输出电压，单位 V。"""
    vin_v = _positive(vin_v, "vin_v")
    r1_ohm = _positive(r1_ohm, "r1_ohm")
    r2_ohm = _positive(r2_ohm, "r2_ohm")
    return vin_v * r2_ohm / (r1_ohm + r2_ohm)


def theoretical_current(
    vin_v: float = 12.0,
    r1_ohm: float = 1_000.0,
    r2_ohm: float = 1_000.0,
) -> float:
    """串联回路电流，单位 A。"""
    vin_v = _positive(vin_v, "vin_v")
    r1_ohm = _positive(r1_ohm, "r1_ohm")
    r2_ohm = _positive(r2_ohm, "r2_ohm")
    return vin_v / (r1_ohm + r2_ohm)

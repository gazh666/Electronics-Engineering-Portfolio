"""RC 充电电路（一阶低通）。

拓扑::

    vin ── R ── out ── C ── gnd
      │
    脉冲电压源

时间常数 tau = R × C；理论响应 Vc(t) = Vin × (1 − exp(−t / tau))。
输入使用有限上升时间（默认 1 μs），与理想瞬时阶跃存在物理差异。
"""

from __future__ import annotations

import math

from PySpice.Spice.Netlist import Circuit


def _positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是数值，实际为 {value!r}")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} 必须是有限正数，实际为 {value!r}")
    return number


def build_rc_charging(
    vin_v: float = 5.0,
    resistance_ohm: float = 1_000.0,
    capacitance_f: float = 1e-6,
    *,
    rise_time_s: float = 1e-6,
    name: str = "RC Charging",
) -> Circuit:
    """构建 RC 充电电路。

    脉冲宽度与周期取得远大于仿真时长，保证整个瞬态区间内输入保持高电平。
    """
    vin_v = _positive(vin_v, "vin_v")
    resistance_ohm = _positive(resistance_ohm, "resistance_ohm")
    capacitance_f = _positive(capacitance_f, "capacitance_f")
    rise_time_s = _positive(rise_time_s, "rise_time_s")

    circuit = Circuit(name)
    circuit.PulseVoltageSource(
        "input",
        "vin",
        circuit.gnd,
        initial_value=0,
        pulsed_value=vin_v,
        delay_time=0,
        rise_time=rise_time_s,
        fall_time=rise_time_s,
        pulse_width=0.02,
        period=0.04,
    )
    circuit.R(1, "vin", "out", resistance_ohm)
    circuit.C(1, "out", circuit.gnd, capacitance_f)
    return circuit


def time_constant(resistance_ohm: float = 1_000.0, capacitance_f: float = 1e-6) -> float:
    """RC 时间常数，单位 s。"""
    resistance_ohm = _positive(resistance_ohm, "resistance_ohm")
    capacitance_f = _positive(capacitance_f, "capacitance_f")
    return resistance_ohm * capacitance_f


def theoretical_voltage(
    time_s: float,
    vin_v: float = 5.0,
    resistance_ohm: float = 1_000.0,
    capacitance_f: float = 1e-6,
) -> float:
    """理想瞬时阶跃下的电容电压理论值，单位 V。"""
    if time_s < 0 or not math.isfinite(time_s):
        raise ValueError(f"time_s 必须是非负有限数，实际为 {time_s!r}")
    tau = time_constant(resistance_ohm, capacitance_f)
    return vin_v * (1.0 - math.exp(-time_s / tau))

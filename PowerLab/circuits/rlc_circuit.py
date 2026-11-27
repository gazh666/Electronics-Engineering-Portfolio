"""串联 RLC 电路：阶跃瞬态与交流频率响应。

拓扑::

    vin ── R ── n1 ── L ── out ── C ── gnd

瞬态用于观察三种阻尼状态；交流分析同时保留电容电压与电感电流响应。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .validators import finite_number, positive_number

DEFAULT_AC_MAGNITUDE_V = 1.0


def build_rlc_transient(
    resistance_ohm: float = 10.0,
    inductance_h: float = 0.01,
    capacitance_f: float = 1e-6,
    *,
    input_v: float = 5.0,
    rise_time_s: float = 1e-6,
    pulse_width_s: float = 50e-3,
    period_s: float = 100e-3,
    name: str = "Series RLC Transient",
) -> Circuit:
    """构建串联 RLC 阶跃瞬态电路。"""
    resistance_ohm = positive_number(resistance_ohm, "resistance_ohm")
    inductance_h = positive_number(inductance_h, "inductance_h")
    capacitance_f = positive_number(capacitance_f, "capacitance_f")
    input_v = finite_number(input_v, "input_v")
    rise_time_s = positive_number(rise_time_s, "rise_time_s")
    pulse_width_s = positive_number(pulse_width_s, "pulse_width_s")
    period_s = positive_number(period_s, "period_s")

    if period_s <= pulse_width_s + 2 * rise_time_s:
        raise ValueError("period_s must exceed pulse_width_s plus rise/fall times")

    circuit = Circuit(name)
    circuit.PulseVoltageSource(
        "input",
        "vin",
        circuit.gnd,
        initial_value=0,
        pulsed_value=input_v,
        delay_time=0,
        rise_time=rise_time_s,
        fall_time=rise_time_s,
        pulse_width=pulse_width_s,
        period=period_s,
    )
    circuit.R(1, "vin", "n1", resistance_ohm)
    circuit.L(1, "n1", "out", inductance_h)
    circuit.C(1, "out", circuit.gnd, capacitance_f)
    return circuit


def build_rlc_ac(
    resistance_ohm: float = 10.0,
    inductance_h: float = 0.01,
    capacitance_f: float = 1e-6,
    *,
    ac_magnitude_v: float = DEFAULT_AC_MAGNITUDE_V,
    name: str = "Series RLC AC",
) -> Circuit:
    """构建串联 RLC 交流小信号电路（节点 out 为电容电压）。"""
    resistance_ohm = positive_number(resistance_ohm, "resistance_ohm")
    inductance_h = positive_number(inductance_h, "inductance_h")
    capacitance_f = positive_number(capacitance_f, "capacitance_f")
    ac_magnitude_v = positive_number(ac_magnitude_v, "ac_magnitude_v")

    circuit = Circuit(name)
    circuit.SinusoidalVoltageSource(
        "input",
        "vin",
        circuit.gnd,
        amplitude=1,
        frequency=1_000,
        ac_magnitude=ac_magnitude_v,
    )
    circuit.R(1, "vin", "n1", resistance_ohm)
    circuit.L(1, "n1", "out", inductance_h)
    circuit.C(1, "out", circuit.gnd, capacitance_f)
    return circuit

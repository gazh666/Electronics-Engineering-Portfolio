"""RC 一阶电路：瞬态充电/放电与交流低通。

拓扑（两种分析共用）::

    vin ── R ── out ── C ── gnd

瞬态使用带有限上升时间的脉冲源；交流分析使用显式 AC 幅值的正弦源。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .validators import finite_number, positive_number

#: 交流小信号默认激励幅值（V），显式写入网表 ``AC 1V``。
DEFAULT_AC_MAGNITUDE_V = 1.0


def build_rc_transient(
    input_v: float = 5.0,
    resistance_ohm: float = 1_000.0,
    capacitance_f: float = 1e-6,
    *,
    rise_time_s: float = 1e-6,
    pulse_width_s: float = 6e-3,
    period_s: float = 12e-3,
    name: str = "RC Transient",
) -> Circuit:
    """构建 RC 充放电瞬态电路。

    默认脉宽 6 ms、周期 12 ms，可在同一段仿真中观察完整充电与放电。
    """
    input_v = finite_number(input_v, "input_v")
    resistance_ohm = positive_number(resistance_ohm, "resistance_ohm")
    capacitance_f = positive_number(capacitance_f, "capacitance_f")
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
    circuit.R(1, "vin", "out", resistance_ohm)
    circuit.C(1, "out", circuit.gnd, capacitance_f)
    return circuit


def build_rc_lowpass(
    resistance_ohm: float = 1_000.0,
    capacitance_f: float = 1e-6,
    *,
    ac_magnitude_v: float = DEFAULT_AC_MAGNITUDE_V,
    name: str = "RC Low Pass Filter",
) -> Circuit:
    """构建 RC 低通交流小信号电路。

    ``SinusoidalVoltageSource`` 在 PySpice 1.5 中会同时写入
    ``DC 0V AC <ac_magnitude>V``，保证 AC 分析具有明确的激励幅值。
    """
    resistance_ohm = positive_number(resistance_ohm, "resistance_ohm")
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
    circuit.R(1, "vin", "out", resistance_ohm)
    circuit.C(1, "out", circuit.gnd, capacitance_f)
    return circuit

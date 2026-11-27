"""RL 一阶电路：阶跃电压下的电感电流上升。

拓扑::

    vin ── R ── inductor_node ── L ── gnd

电感电流连续，是后续 Buck 电路的基础。仿真结束前不施加下降沿，
避免在无续流路径时讨论电流突变。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .validators import finite_number, positive_number


def build_rl_transient(
    input_v: float = 5.0,
    resistance_ohm: float = 10.0,
    inductance_h: float = 0.01,
    *,
    rise_time_s: float = 1e-6,
    pulse_width_s: float = 20e-3,
    period_s: float = 40e-3,
    name: str = "RL Transient",
) -> Circuit:
    """构建 RL 阶跃瞬态电路。"""
    input_v = finite_number(input_v, "input_v")
    resistance_ohm = positive_number(resistance_ohm, "resistance_ohm")
    inductance_h = positive_number(inductance_h, "inductance_h")
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
    circuit.R(1, "vin", "inductor_node", resistance_ohm)
    circuit.L(1, "inductor_node", circuit.gnd, inductance_h)
    return circuit

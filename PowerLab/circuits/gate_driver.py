"""高侧 N 沟道 MOSFET 栅极驱动。

参考结构::

    VDRV drv sw PULSE(0 10 10u 20n 20n 4.1466667u 10u)
    RG   drv gate 10
    RGS  gate sw 100k

``VDRV`` 的负端接 MOSFET 源极（开关节点 ``sw``），因此
``VGS = V(gate) - V(sw)``，而不是 ``V(gate)`` 对地电压。

这是理想浮动驱动源，不是真实 Bootstrap 电路：
本阶段没有建模自举电容充电、驱动芯片供电、欠压锁定（UVLO）与死区。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .nonideal_config import GateDriverConfig
from .pwm import PWMParameters
from .validators import finite_number, positive_number

#: 驱动电源、栅极电阻、下拉电阻的默认实例名。
DRIVER_SOURCE_NAME = "DRV"
GATE_RESISTOR_NAME = "G"
PULLDOWN_RESISTOR_NAME = "GS"


def add_floating_gate_driver(
    circuit: Circuit,
    pwm: PWMParameters,
    config: GateDriverConfig,
    *,
    source_node: str = "sw",
    gate_node: str = "gate",
    drive_node: str = "drv",
) -> dict[str, str]:
    """添加以开关节点为参考的理想浮动驱动，返回节点与元件名。"""
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(pwm, PWMParameters):
        raise ValueError("pwm must be PWMParameters")
    if not isinstance(config, GateDriverConfig):
        raise ValueError("config must be GateDriverConfig")
    for value, name in (
        (source_node, "source_node"),
        (gate_node, "gate_node"),
        (drive_node, "drive_node"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty node name")
    if len({source_node, gate_node, drive_node}) != 3:
        raise ValueError("source, gate and drive nodes must be distinct")

    circuit.PulseVoltageSource(
        DRIVER_SOURCE_NAME,
        drive_node,
        source_node,
        initial_value=config.low_voltage_v,
        pulsed_value=config.drive_voltage_v,
        delay_time=pwm.delay_s,
        rise_time=pwm.rise_time_s,
        fall_time=pwm.fall_time_s,
        pulse_width=pwm.pulse_width_s,
        period=pwm.period_s,
    )
    circuit.R(GATE_RESISTOR_NAME, drive_node, gate_node, config.gate_resistance_ohm)
    circuit.R(
        PULLDOWN_RESISTOR_NAME,
        gate_node,
        source_node,
        config.gate_source_pulldown_ohm,
    )
    return {
        "driver_source": f"V{DRIVER_SOURCE_NAME}",
        "gate_resistor": f"R{GATE_RESISTOR_NAME}",
        "pulldown_resistor": f"R{PULLDOWN_RESISTOR_NAME}",
        "drive_node": drive_node,
        "gate_node": gate_node,
        "source_node": source_node,
    }


def add_ground_referenced_gate_drive(
    circuit: Circuit,
    pwm: PWMParameters,
    gate_node: str = "gate",
    *,
    name: str = "PWM",
) -> str:
    """添加对地参考的 PWM 栅极激励（用于 SW 开关对照模型 A/B/C）。

    这不是高侧浮动驱动：它直接驱动对地参考的电压控制开关。
    """
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(pwm, PWMParameters):
        raise ValueError("pwm must be PWMParameters")
    if not isinstance(gate_node, str) or not gate_node.strip():
        raise ValueError("gate_node must be a non-empty node name")
    instance = str(name).strip()
    if not instance:
        raise ValueError("gate drive source name must be a non-empty string")
    circuit.PulseVoltageSource(
        instance,
        gate_node,
        circuit.gnd,
        initial_value=pwm.low_voltage_v,
        pulsed_value=pwm.high_voltage_v,
        delay_time=pwm.delay_s,
        rise_time=pwm.rise_time_s,
        fall_time=pwm.fall_time_s,
        pulse_width=pwm.pulse_width_s,
        period=pwm.period_s,
    )
    return f"V{instance}"


def gate_resistor_current_a(
    drive_voltage_v: float,
    gate_voltage_v: float,
    gate_resistance_ohm: float,
) -> float:
    """由真实节点电压与已知栅极电阻计算 ``IG = (Vdrv - Vgate) / RG``。"""
    resistance = positive_number(gate_resistance_ohm, "gate_resistance_ohm")
    return (finite_number(drive_voltage_v, "drive_voltage_v") - finite_number(
        gate_voltage_v, "gate_voltage_v"
    )) / resistance


def pulldown_current_a(
    gate_voltage_v: float,
    source_voltage_v: float,
    pulldown_resistance_ohm: float,
) -> float:
    """由真实 VGS 与已知下拉电阻计算 ``IRGS = VGS / RGS``。"""
    resistance = positive_number(pulldown_resistance_ohm, "pulldown_resistance_ohm")
    return (
        finite_number(gate_voltage_v, "gate_voltage_v")
        - finite_number(source_voltage_v, "source_voltage_v")
    ) / resistance

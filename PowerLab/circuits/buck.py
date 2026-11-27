"""非同步 Buck 降压变换器拓扑构建。

拓扑（节点名与实际网表一致）::

    vin ── S1(vin→sw, gate 控制) ── sw ── VSENSE ── lx ── L1 ── out ──┬── C1 ── GND
                                     │                                  └── RLOAD ── GND
                                    DFREE（阳极 GND、阴极 sw）

``VSENSE`` 是 0 V 电压源，用于获取流过电感的真实支路电流；
它不改变电路拓扑，但必须保留，否则无法从 ngspice 取得电感电流。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .buck_config import BuckParameters, BuckConfig
from .pwm import PWMParameters
from .switch_models import (
    SWITCH_MODEL_NAME,
    DiodeConfig,
    SwitchConfig,
    add_diode_model,
    add_switch_model,
)

DEFAULT_CIRCUIT_TITLE = "PowerLab Basic Asynchronous Buck"

#: 供分析层使用的节点 / 支路名称。
NODE_VIN = "vin"
NODE_GATE = "gate"
NODE_SWITCH = "sw"
NODE_INDUCTOR = "lx"
NODE_OUTPUT = "out"
BRANCH_INPUT = "vin"
BRANCH_SENSE = "vsense"


def build_buck_circuit(
    buck_config: BuckConfig,
    pwm_config: PWMParameters,
    switch_config: SwitchConfig,
    diode_config: DiodeConfig,
    *,
    title: str = DEFAULT_CIRCUIT_TITLE,
) -> Circuit:
    """按实际参数构建 Buck 电路（不执行仿真）。"""
    if not isinstance(buck_config, BuckConfig):
        raise ValueError("buck_config must be BuckConfig")
    if not isinstance(pwm_config, PWMParameters):
        raise ValueError("pwm_config must be PWMParameters")
    if not isinstance(switch_config, SwitchConfig):
        raise ValueError("switch_config must be SwitchConfig")
    if not isinstance(diode_config, DiodeConfig):
        raise ValueError("diode_config must be DiodeConfig")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")

    circuit = Circuit(title.strip())

    circuit.V("IN", NODE_VIN, circuit.gnd, buck_config.input_voltage_v)

    circuit.PulseVoltageSource(
        "PWM",
        NODE_GATE,
        circuit.gnd,
        initial_value=pwm_config.low_voltage_v,
        pulsed_value=pwm_config.high_voltage_v,
        delay_time=pwm_config.delay_s,
        rise_time=pwm_config.rise_time_s,
        fall_time=pwm_config.fall_time_s,
        pulse_width=pwm_config.pulse_width_s,
        period=pwm_config.period_s,
    )

    switch_model = add_switch_model(circuit, switch_config, name=SWITCH_MODEL_NAME)
    circuit.S(1, NODE_VIN, NODE_SWITCH, NODE_GATE, circuit.gnd, model=switch_model)

    diode_model = add_diode_model(circuit, diode_config)
    # 阳极接 GND、阴极接 sw：开关关断时电感电流经二极管续流。
    circuit.D("FREE", circuit.gnd, NODE_SWITCH, model=diode_model)

    circuit.V("SENSE", NODE_SWITCH, NODE_INDUCTOR, 0.0)
    circuit.L(1, NODE_INDUCTOR, NODE_OUTPUT, buck_config.inductance_h)
    circuit.C(1, NODE_OUTPUT, circuit.gnd, buck_config.capacitance_f)
    circuit.R("LOAD", NODE_OUTPUT, circuit.gnd, buck_config.load_resistance_ohm)

    return circuit


def build_buck_from_parameters(
    parameters: BuckParameters,
    *,
    title: str | None = None,
) -> Circuit:
    """用聚合配置构建 Buck 电路。"""
    if not isinstance(parameters, BuckParameters):
        raise ValueError("parameters must be BuckParameters")
    return build_buck_circuit(
        parameters.circuit,
        parameters.pwm,
        parameters.switch,
        parameters.diode,
        title=title or parameters.circuit_name,
    )

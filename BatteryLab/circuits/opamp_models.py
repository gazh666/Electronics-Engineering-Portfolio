"""运放三层模型（Task 5）。

A. 理想运放：高增益 VCVS，仅用于教学参考。
B. 教学非理想运放：有限开环增益、输入失调、输出饱和、单极点带宽。
C. 规格参考行为模型：用于 INA240A2，仅依据官方规格构造行为模型，
   不是厂商内部晶体管级 SPICE 模型，也不宣称复现全部 PWM 抑制能力。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_F, u_Hz, u_Ohm

GIGA_OHM = 1e9


class OpAmpModelError(ValueError):
    """运放模型参数非法。"""


@dataclass(frozen=True)
class OpAmpSpec:
    name: str = "opamp"
    model_kind: str = "ideal"  # ideal / teaching_nonideal / spec_reference
    open_loop_gain: float = 1_000_000.0
    output_low_v: float = 0.05
    output_high_v: float = 4.95
    input_offset_v: float = 0.0
    input_bias_current_a: float = 0.0
    gain_bandwidth_hz: float | None = None
    input_common_mode_min_v: float = 0.0
    input_common_mode_max_v: float = 5.0

    def __post_init__(self) -> None:
        for label, value in (
            ("open_loop_gain", self.open_loop_gain),
            ("output_low_v", self.output_low_v),
            ("output_high_v", self.output_high_v),
            ("input_offset_v", self.input_offset_v),
            ("input_bias_current_a", self.input_bias_current_a),
        ):
            if not math.isfinite(value):
                raise OpAmpModelError(f"{label} 必须为有限值")
        if self.open_loop_gain <= 0.0:
            raise OpAmpModelError("开环增益必须为正")
        if self.output_low_v >= self.output_high_v:
            raise OpAmpModelError("输出下限必须小于上限")
        if self.gain_bandwidth_hz is not None and self.gain_bandwidth_hz <= 0.0:
            raise OpAmpModelError("增益带宽积必须为正")


def _ground(circuit: Circuit, node: str | None) -> str:
    return circuit.gnd if node is None else node


def add_opamp(
    circuit: Circuit,
    spec: OpAmpSpec,
    *,
    output_node: str,
    non_inverting_node: str,
    inverting_node: str,
    ground_node: str | None = None,
    pole_resistance_ohm: float = 1000.0,
) -> dict[str, str]:
    """把运放模型加入电路，返回内部节点名。

    输出级使用 ``min(max(...))`` 实现输出电压饱和；反馈从饱和后的输出节点
    取回，因此饱和时虚短近似失效的行为可以被真实 SPICE 求解反映出来。
    """
    ground = _ground(circuit, ground_node)
    internal = f"int_{spec.name}"
    filtered = f"intf_{spec.name}"

    effective_inverting = inverting_node
    if spec.input_offset_v:
        offset_node = f"inm_off_{spec.name}"
        circuit.V(f"off_{spec.name}", inverting_node, offset_node, spec.input_offset_v)
        effective_inverting = offset_node

    if spec.model_kind == "ideal":
        circuit.VCVS(spec.name, output_node, ground, non_inverting_node, effective_inverting, voltage_gain=spec.open_loop_gain)
        return {"internal": output_node, "filtered": output_node, "output": output_node}

    circuit.VCVS(spec.name, internal, ground, non_inverting_node, effective_inverting, voltage_gain=spec.open_loop_gain)

    if spec.gain_bandwidth_hz:
        pole_hz = spec.gain_bandwidth_hz / spec.open_loop_gain
        capacitance = 1.0 / (2.0 * math.pi * pole_hz * pole_resistance_ohm)
        circuit.R(f"pole_{spec.name}", internal, filtered, pole_resistance_ohm)
        circuit.C(f"pole_{spec.name}", filtered, ground, capacitance)
    else:
        circuit.R(f"link_{spec.name}", internal, filtered, 1.0e-3)

    # 使用平滑 tanh 饱和，避免 min/max 非光滑函数在反馈环路中导致不收敛。
    midpoint = 0.5 * (spec.output_low_v + spec.output_high_v)
    half_span = 0.5 * (spec.output_high_v - spec.output_low_v)
    expression = f"{midpoint}+{half_span}*tanh((V({filtered})-{midpoint})/{half_span})"
    circuit.B(f"clamp_{spec.name}", output_node, ground, v=expression)

    if spec.input_bias_current_a:
        circuit.I(f"ib_p_{spec.name}", ground, non_inverting_node, spec.input_bias_current_a)
        circuit.I(f"ib_n_{spec.name}", ground, inverting_node, spec.input_bias_current_a)

    return {"internal": internal, "filtered": filtered, "output": output_node}


@dataclass(frozen=True)
class CurrentAmplifierSpec:
    """规格参考电流放大器行为模型（INA240A2 规格）。"""

    name: str = "ina240"
    gain: float = 50.0
    reference_voltage_v: float = 1.65
    input_offset_v: float = 0.0
    gain_error_fraction: float = 0.0
    cmrr_db: float | None = 132.0
    bandwidth_hz: float | None = 400_000.0
    output_low_v: float = 0.1
    output_high_v: float = 4.9
    pole_resistance_ohm: float = 1000.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.gain) or self.gain <= 0.0:
            raise OpAmpModelError("电流放大器增益必须为正")
        if not math.isfinite(self.reference_voltage_v):
            raise OpAmpModelError("参考电压必须有限")
        if self.output_low_v >= self.output_high_v:
            raise OpAmpModelError("输出范围非法")
        if self.bandwidth_hz is not None and self.bandwidth_hz <= 0.0:
            raise OpAmpModelError("带宽必须为正")

    @property
    def common_mode_gain(self) -> float:
        if self.cmrr_db is None:
            return 0.0
        return self.gain / (10.0 ** (self.cmrr_db / 20.0))


def add_spec_reference_current_amplifier(
    circuit: Circuit,
    spec: CurrentAmplifierSpec,
    *,
    output_node: str,
    srp_node: str,
    srn_node: str,
    ground_node: str | None = None,
) -> dict[str, str]:
    """加入规格参考电流放大器行为模型。

    模型包含：差分增益、输入失调、增益误差、有限 CMRR 引起的共模泄漏、
    单极点有限带宽、输出电压饱和。
    """
    ground = _ground(circuit, ground_node)
    raw = f"raw_{spec.name}"
    filtered = f"intf_{spec.name}"
    effective_gain = spec.gain * (1.0 + spec.gain_error_fraction)
    acm = spec.common_mode_gain
    expression = (
        f"{spec.reference_voltage_v}"
        f"+{effective_gain}*(V({srp_node})-V({srn_node}))"
        f"+{effective_gain * spec.input_offset_v}"
        f"+{acm}*0.5*(V({srp_node})+V({srn_node}))"
    )
    circuit.B(f"raw_{spec.name}", raw, ground, v=expression)

    if spec.bandwidth_hz:
        capacitance = 1.0 / (2.0 * math.pi * spec.bandwidth_hz * spec.pole_resistance_ohm)
        circuit.R(f"pole_{spec.name}", raw, filtered, spec.pole_resistance_ohm)
        circuit.C(f"pole_{spec.name}", filtered, ground, capacitance)
    else:
        circuit.R(f"link_{spec.name}", raw, filtered, 1.0e-3)

    clamp_expression = f"min(max(V({filtered}),{spec.output_low_v}),{spec.output_high_v})"
    circuit.B(f"clamp_{spec.name}", output_node, ground, v=clamp_expression)
    return {"raw": raw, "filtered": filtered, "output": output_node}


def current_amplifier_from_config(config: dict) -> CurrentAmplifierSpec:
    amp = config["amplifier"]
    return CurrentAmplifierSpec(
        name="ina240",
        gain=float(amp["gain_v_per_v"]),
        reference_voltage_v=float(amp["reference_voltage_v"]),
        input_offset_v=0.0,
        gain_error_fraction=0.0,
        cmrr_db=float(amp["cmrr_db_typ"]),
        bandwidth_hz=float(amp["bandwidth_hz"]),
        output_low_v=float(amp["output_low_v"]),
        output_high_v=float(amp["output_high_v"]),
    )

"""把 PI 控制律写成 ngspice 行为源（真实仿真内闭环）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySpice.Spice.Netlist import Circuit

from circuits.validators import finite_number, positive_number

from .anti_windup import clamp_duty
from .models import CarrierConfig, ControllerConfig, SoftStartConfig
from .soft_start import soft_start_points


@dataclass(frozen=True)
class SpiceControllerLayout:
    """行为控制器在网表中的节点与元件名。"""

    nodes: dict[str, str]
    elements: dict[str, str]
    expressions: dict[str, str]
    reference_points: list[tuple[float, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": dict(self.nodes),
            "elements": dict(self.elements),
            "expressions": dict(self.expressions),
            "reference_points": [[float(t), float(v)] for t, v in self.reference_points],
        }


def _integral_expression(config: ControllerConfig) -> str:
    ki = config.ki
    if config.anti_windup == "none":
        return f"{ki:.12g}*V(err)"
    if config.anti_windup == "back_calculation":
        return (
            f"{ki:.12g}*V(err)+{config.tracking_gain:.12g}*"
            f"(V(duty)-V(raw))"
        )
    # conditional：只在未向上饱和时累积正误差，未向下饱和时累积负误差。
    gate_up = (
        f"min(max(({config.duty_max:.12g}-V(raw))/0.002,0),1)"
    )
    gate_down = f"min(max((V(raw)-{config.duty_min:.12g})/0.002,0),1)"
    return (
        f"{ki:.12g}*(max(V(err),0)*{gate_up}"
        f"+min(V(err),0)*{gate_down})"
    )


def add_behavioral_pi_controller(
    circuit: Circuit,
    config: ControllerConfig,
    soft_start: SoftStartConfig,
    carrier: CarrierConfig,
    *,
    target_v: float,
    vin_node: str = "vin",
    output_node: str = "out",
    end_time_s: float,
    prefix: str = "C",
    drive_mode: str = "mosfet",
    switch_control_node: str = "ctrl",
    switch_drive_voltage_v: float = 5.0,
) -> SpiceControllerLayout:
    """把参考、误差、前馈、PI、限幅、载波、比较器加入电路。

    元件名统一加 ``prefix`` 前缀，避免与功率级冲突。
    ``drive_mode="mosfet"`` 生成以 ``sw`` 为参考的浮动 VCVS 驱动；
    ``drive_mode="switch"`` 生成 0—5 V 的开关控制信号（最小 SW 模型）。
    """
    target = positive_number(target_v, "target_v")
    if drive_mode not in ("mosfet", "switch"):
        raise ValueError("drive_mode must be 'mosfet' or 'switch'")
    if carrier.carrier_type != "sine":
        raise ValueError(
            "SPICE closed-loop implementation supports only the sine carrier; "
            "sawtooth is available in the averaged/PWM analysis tools"
        )
    clamp_duty(config.duty_min, config.duty_min, config.duty_max)  # 校验限幅
    duration = soft_start.duration_s
    points = soft_start_points(
        target,
        duration,
        initial_v=soft_start.initial_reference_v,
        end_time_s=end_time_s,
        enabled=soft_start.enabled,
    )
    width = carrier.smoothing_width
    frequency = carrier.frequency_hz
    kp = finite_number(config.kp, "controller.kp")
    vin_min = config.vin_min_for_feedforward_v

    elements = {
        "reference": f"V{prefix}REF",
        "error": f"B{prefix}ERR",
        "feedforward": f"B{prefix}FF",
        "proportional": f"B{prefix}PROP",
        "raw": f"B{prefix}RAW",
        "limit": f"B{prefix}LIM",
        "integrator_capacitor": f"C{prefix}INT",
        "integrator_current": f"B{prefix}IINT",
        "integrator_leak": f"R{prefix}ILEAK",
        "carrier": f"B{prefix}RAMP",
        "comparator": f"B{prefix}PWM",
        "driver": f"E{prefix}DRV" if drive_mode == "mosfet" else f"B{prefix}CTRL",
        "gate_resistor": f"R{prefix}G" if drive_mode == "mosfet" else "",
        "gate_pulldown": f"R{prefix}GS" if drive_mode == "mosfet" else "",
    }

    circuit.PieceWiseLinearVoltageSource(
        "CREF" if prefix == "C" else f"{prefix}REF",
        "ref",
        circuit.gnd,
        values=points,
    )
    circuit.B("CERR" if prefix == "C" else f"{prefix}ERR", "err", circuit.gnd,
              voltage_expression=f"V(ref)-V({output_node})")
    feedforward_expression = (
        f"V(ref)/max(V({vin_node}),{vin_min:.12g})"
        if config.feedforward_enabled
        else "0"
    )
    circuit.B("CFF" if prefix == "C" else f"{prefix}FF", "ff", circuit.gnd,
              voltage_expression=feedforward_expression)
    circuit.B("CPROP" if prefix == "C" else f"{prefix}PROP", "prop", circuit.gnd,
              voltage_expression=f"{kp:.12g}*V(err)")
    circuit.B("CRAW" if prefix == "C" else f"{prefix}RAW", "raw", circuit.gnd,
              voltage_expression="V(ff)+V(prop)+V(integ)")
    circuit.B(
        "CLIM" if prefix == "C" else f"{prefix}LIM",
        "duty",
        circuit.gnd,
        voltage_expression=(
            f"min(max(V(raw),{config.duty_min:.12g}),{config.duty_max:.12g})"
        ),
    )
    circuit.C("CINT" if prefix == "C" else f"{prefix}INT", "integ", circuit.gnd, 1.0, ic=0)
    circuit.B(
        "CIINT" if prefix == "C" else f"{prefix}IINT",
        circuit.gnd,
        "integ",
        current_expression=_integral_expression(config),
    )
    # 1 GΩ 漏电阻只用于避免工作点矩阵奇异，时间常数 1e9 s，不影响 100 kHz 环路。
    circuit.R("CILEAK" if prefix == "C" else f"{prefix}ILEAK", "integ", circuit.gnd, 1e9)
    circuit.B(
        "CRAMP" if prefix == "C" else f"{prefix}RAMP",
        "ramp",
        circuit.gnd,
        voltage_expression=(
            f"0.5*(1+sin({2.0 * 3.141592653589793 * frequency:.12g}*time))"
        ),
    )
    circuit.B(
        "CPWM" if prefix == "C" else f"{prefix}PWM",
        "pwm",
        circuit.gnd,
        voltage_expression=(
            f"min(max((V(duty)-V(ramp))/{width:.12g}+0.5,0),1)"
        ),
    )
    if drive_mode == "mosfet":
        circuit.VCVS(
            "CDRV" if prefix == "C" else f"{prefix}DRV",
            "drv",
            "sw",
            "pwm",
            circuit.gnd,
            10.0,
        )
        circuit.R("CG" if prefix == "C" else f"{prefix}G", "drv", "gate", 10.0)
        circuit.R("CGS" if prefix == "C" else f"{prefix}GS", "gate", "sw", 100e3)
    else:
        circuit.B(
            "CCTRL" if prefix == "C" else f"{prefix}CTRL",
            switch_control_node,
            circuit.gnd,
            voltage_expression=f"{switch_drive_voltage_v:.12g}*V(pwm)",
        )

    nodes = {
        "ref": "ref",
        "err": "err",
        "ff": "ff",
        "prop": "prop",
        "raw": "raw",
        "duty": "duty",
        "integ": "integ",
        "ramp": "ramp",
        "pwm": "pwm",
        "drv": "drv" if drive_mode == "mosfet" else switch_control_node,
        "gate": "gate" if drive_mode == "mosfet" else "",
        "sw": "sw",
    }
    expressions = {
        "error": f"V(ref)-V({output_node})",
        "feedforward": feedforward_expression,
        "proportional": f"{kp:.12g}*V(err)",
        "raw": "V(ff)+V(prop)+V(integ)",
        "limit": f"min(max(V(raw),{config.duty_min:.12g}),{config.duty_max:.12g})",
        "integral": _integral_expression(config),
        "carrier": f"0.5*(1+sin({2.0 * 3.141592653589793 * frequency:.12g}*time))",
        "comparator": f"min(max((V(duty)-V(ramp))/{width:.12g}+0.5,0),1)",
        "driver": (
            "10*V(pwm)"
            if drive_mode == "mosfet"
            else f"{switch_drive_voltage_v:.12g}*V(pwm)"
        ),
        "drive_mode": drive_mode,
    }
    return SpiceControllerLayout(
        nodes=nodes,
        elements=elements,
        expressions=expressions,
        reference_points=points,
    )

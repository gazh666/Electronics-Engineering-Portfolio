"""第七阶段闭环 Buck 电路构建器。

在第四阶段非理想功率级基础上组合动态输入源、动态负载与行为 PI 控制器。
功率级器件直接复用 ``circuits`` 包中的已有构建函数，不复制器件模型参数。

支持的功率级模型：

========  ==========  ==============  ==========  ====  ====
变体      主开关      续流二极管      驱动方式    DCR   ESR
========  ==========  ==============  ==========  ====  ====
E         NMOS + 寄生  非理想二极管    浮动 VCVS   是    是
D         NMOS        非理想二极管    浮动 VCVS   是    是
SW        SW 开关      教学理想二极管  对地 0—5 V  否    否
========  ==========  ==============  ==========  ====  ====

``mode="closed_loop"`` 时由行为源在仿真过程中读取 ``V(out)`` 并调整 PWM；
``mode="open_loop"`` 时使用固定占空比 PULSE 源，作为公平对照基线。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySpice.Spice.Netlist import Circuit

from control.models import CarrierConfig, ControllerConfig, SoftStartConfig
from control.spice_controller import SpiceControllerLayout, add_behavioral_pi_controller

from .closed_loop_config import SUPPORTED_MODES, ClosedLoopConfig
from .diode_models import add_nonideal_diode
from .dynamic_load import CurrentStepLoad, ResistiveStepLoad
from .gate_driver import add_floating_gate_driver, add_ground_referenced_gate_drive
from .input_disturbance import add_input_source
from .mosfet_models import add_educational_nmos, add_mosfet_parasitic_capacitors
from .nonideal_buck import LEGACY_DIODE, NODE_SWITCH
from .nonideal_config import InductorModelConfig, CapacitorModelConfig
from .passive_models import add_capacitor_with_esr, add_inductor_with_dcr
from .pwm import PWMParameters
from .switch_models import SWITCH_MODEL_NAME, SwitchConfig, add_diode_model, add_switch_model

NODE_INPUT = "vin"
NODE_DRAIN = "drain"
NODE_GATE = "gate"
NODE_SWITCH = "sw"
NODE_DIODE_ANODE = "diode_a"
NODE_INDUCTOR = "lx"
NODE_INDUCTOR_DCR = "l_dcr"
NODE_OUTPUT = "out"
NODE_CAPACITOR_ESR = "c_esr"
NODE_CAPACITOR_INTERNAL = "cap_internal"
NODE_LOAD = "load_node"
NODE_SWITCH_CONTROL = "ctrl"

#: 最小 SW 闭环使用的开关参数。闭环里把迟滞压到 0.02 V（栅极 5 V 的 0.4%），
#: 避免教学开关的 2% 迟滞主导环路、产生与真实电路无关的极限环。
SWITCH_MODEL = SwitchConfig(
    on_resistance_ohm=1e-3,
    off_resistance_ohm=1e6,
    threshold_voltage_v=2.5,
    hysteresis_voltage_v=0.02,
)
SWITCH_GATE_HIGH_V = 5.0


@dataclass(frozen=True)
class ClosedLoopLayout:
    """闭环电路在网表中的节点、元件与支路映射。"""

    variant: str
    mode: str
    nodes: dict[str, str]
    elements: dict[str, str]
    branches: dict[str, str]
    features: dict[str, Any]
    controller: SpiceControllerLayout | None
    load: dict[str, Any]
    line: dict[str, Any]
    title: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "mode": self.mode,
            "title": self.title,
            "nodes": dict(self.nodes),
            "elements": dict(self.elements),
            "branches": dict(self.branches),
            "features": dict(self.features),
            "load": dict(self.load),
            "line": dict(self.line),
            "controller": self.controller.to_dict() if self.controller else None,
        }


def _power_stage_passives(config: ClosedLoopConfig) -> tuple[InductorModelConfig, CapacitorModelConfig]:
    """SW 与 MOSFET 变体共用同一组无源寄生参数，避免人为制造零阻尼功率级。"""
    return config.power_stage.inductor, config.power_stage.capacitor


def _open_loop_pwm(config: ClosedLoopConfig, high_voltage_v: float) -> PWMParameters:
    driver = config.power_stage.gate_driver
    return PWMParameters(
        frequency_hz=config.power_stage.switching_frequency_hz,
        duty_cycle=config.open_loop_duty_cycle,
        low_voltage_v=0.0,
        high_voltage_v=high_voltage_v,
        rise_time_s=driver.rise_time_s,
        fall_time_s=driver.fall_time_s,
        delay_s=driver.delay_s,
    )


def build_closed_loop_buck(
    config: ClosedLoopConfig,
    *,
    mode: str = "closed_loop",
    title: str | None = None,
) -> tuple[Circuit, ClosedLoopLayout]:
    """构建闭环或固定占空比开环 Buck，返回 ``(circuit, layout)``。"""
    if not isinstance(config, ClosedLoopConfig):
        raise ValueError("config must be ClosedLoopConfig")
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"mode must be one of {SUPPORTED_MODES}, got {mode!r}")
    variant = config.variant
    end_time = config.end_time_s
    ps = config.power_stage

    circuit_title = title or f"PowerLab Stage-7 Buck {variant} ({mode})"
    circuit = Circuit(circuit_title)

    # ---------------------------------------------------------- 输入源
    line_layout = add_input_source(
        circuit, config.line, end_time, vin_node=NODE_INPUT, name="VIN"
    )

    # ---------------------------------------------------------- 功率级
    circuit.V("DSENSE", NODE_INPUT, NODE_DRAIN, 0.0)
    if variant in ("E", "D"):
        add_educational_nmos(circuit, ps.mosfet, NODE_DRAIN, NODE_GATE, NODE_SWITCH)
        if variant == "E":
            add_mosfet_parasitic_capacitors(
                circuit, ps.mosfet, NODE_DRAIN, NODE_GATE, NODE_SWITCH
            )
    else:
        model = add_switch_model(circuit, SWITCH_MODEL, name=SWITCH_MODEL_NAME)
        control_node = NODE_SWITCH_CONTROL if mode == "closed_loop" else NODE_GATE
        circuit.S("1", NODE_DRAIN, NODE_SWITCH, control_node, circuit.gnd, model=model)

    circuit.V("DIOSENSE", circuit.gnd, NODE_DIODE_ANODE, 0.0)
    if variant in ("E", "D"):
        add_nonideal_diode(circuit, ps.diode, NODE_DIODE_ANODE, NODE_SWITCH)
    else:
        model = add_diode_model(circuit, LEGACY_DIODE)
        circuit.D("FREE", NODE_DIODE_ANODE, NODE_SWITCH, model=model)

    inductor, capacitor = _power_stage_passives(config)
    circuit.V("LSENSE", NODE_SWITCH, NODE_INDUCTOR, 0.0)
    add_inductor_with_dcr(
        circuit,
        inductor,
        NODE_INDUCTOR,
        NODE_OUTPUT,
        internal_node=NODE_INDUCTOR_DCR,
    )
    circuit.V("CSENSE", NODE_OUTPUT, NODE_CAPACITOR_ESR, 0.0)
    add_capacitor_with_esr(
        circuit,
        capacitor,
        NODE_CAPACITOR_ESR,
        circuit.gnd,
        internal_node=NODE_CAPACITOR_INTERNAL,
    )

    # ---------------------------------------------------------- 负载
    circuit.V("LOADSENSE", NODE_OUTPUT, NODE_LOAD, 0.0)
    if config.load is None:
        circuit.R("LOAD", NODE_LOAD, circuit.gnd, ps.load_resistance_ohm)
        load_layout: dict[str, Any] = {
            "load_type": "resistive_fixed",
            "resistance_ohm": ps.load_resistance_ohm,
            "load_element": "RLOAD",
        }
    elif isinstance(config.load, CurrentStepLoad):
        load_layout = config.load.add_to(circuit, NODE_LOAD, circuit.gnd)
    elif isinstance(config.load, ResistiveStepLoad):
        load_layout = config.load.add_to(circuit, NODE_LOAD, circuit.gnd)
    else:  # pragma: no cover - 配置层已校验
        raise ValueError(f"unsupported load type {type(config.load).__name__}")

    # ---------------------------------------------------------- 控制与驱动
    controller_layout: SpiceControllerLayout | None = None
    drive_mode = "switch" if variant == "SW" else "mosfet"
    if mode == "closed_loop":
        controller_layout = add_behavioral_pi_controller(
            circuit,
            config.controller,
            config.soft_start,
            config.carrier,
            target_v=config.target_voltage_v,
            vin_node=NODE_INPUT,
            output_node=NODE_OUTPUT,
            end_time_s=end_time,
            drive_mode=drive_mode,
            switch_control_node=NODE_SWITCH_CONTROL,
            switch_drive_voltage_v=SWITCH_GATE_HIGH_V,
        )
    else:
        if variant in ("E", "D"):
            add_floating_gate_driver(
                circuit,
                _open_loop_pwm(config, ps.gate_driver.drive_voltage_v),
                ps.gate_driver,
                source_node=NODE_SWITCH,
                gate_node=NODE_GATE,
                drive_node="drv",
            )
        else:
            add_ground_referenced_gate_drive(
                circuit,
                _open_loop_pwm(config, SWITCH_GATE_HIGH_V),
                NODE_GATE,
                name="PWM",
            )

    elements = {
        "input_source": "VIN",
        "input_current_sense": "VDSENSE",
        "main_switch": "M1" if variant in ("E", "D") else "S1",
        "freewheel_diode": "DFREE" if variant in ("E", "D") else "DFREE",
        "inductor": "L1",
        "inductor_dcr": "RDCR" if inductor.dcr_ohm > 0 else "",
        "output_capacitor": "C1",
        "capacitor_esr": "RESR" if capacitor.esr_ohm > 0 else "",
        "inductor_current_sense": "VLSENSE",
        "capacitor_current_sense": "VCSENSE",
        "load_current_sense": "VLOADSENSE",
        "load_element": load_layout.get("load_element", "RLOAD"),
        "gate_driver": (
            controller_layout.elements["driver"]
            if controller_layout
            else ("VDRV" if variant in ("E", "D") else "VPWM")
        ),
        "gate_resistor": (
            controller_layout.elements["gate_resistor"]
            if controller_layout
            else ("RG" if variant in ("E", "D") else "")
        ),
        "gate_pulldown": (
            controller_layout.elements["gate_pulldown"]
            if controller_layout
            else ("RGS" if variant in ("E", "D") else "")
        ),
        "switch_control": controller_layout.elements["driver"] if variant == "SW" and controller_layout else "",
    }

    nodes = {
        "input": NODE_INPUT,
        "drain": NODE_DRAIN,
        "gate": NODE_GATE,
        "switch": NODE_SWITCH,
        "diode_anode": NODE_DIODE_ANODE,
        "inductor": NODE_INDUCTOR,
        "inductor_dcr": NODE_INDUCTOR_DCR,
        "output": NODE_OUTPUT,
        "capacitor_esr": NODE_CAPACITOR_ESR,
        "capacitor_internal": NODE_CAPACITOR_INTERNAL,
        "load": NODE_LOAD,
        "switch_control": NODE_SWITCH_CONTROL if variant == "SW" else "",
        "drive": "drv" if variant in ("E", "D") else "",
    }
    if controller_layout is not None:
        nodes.update(
            {
                "reference": controller_layout.nodes["ref"],
                "error": controller_layout.nodes["err"],
                "feedforward": controller_layout.nodes["ff"],
                "proportional": controller_layout.nodes["prop"],
                "integral": controller_layout.nodes["integ"],
                "raw_duty": controller_layout.nodes["raw"],
                "limited_duty": controller_layout.nodes["duty"],
                "carrier": controller_layout.nodes["ramp"],
                "pwm": controller_layout.nodes["pwm"],
            }
        )

    branches = {
        "input_current": "vdsense",
        "inductor_current": "vlsense",
        "capacitor_current": "vcsense",
        "load_current": "vloadsense",
        "diode_current": "vdiosense",
    }
    if variant in ("E", "D") and mode == "open_loop":
        branches["driver_current"] = "vdrv"

    features = {
        "uses_mosfet": variant in ("E", "D"),
        "uses_parasitic_capacitors": variant == "E",
        "uses_nonideal_diode": variant in ("E", "D"),
        "uses_dcr": inductor.dcr_ohm > 0,
        "uses_esr": capacitor.esr_ohm > 0,
        "uses_floating_driver": variant in ("E", "D"),
        "uses_behavioral_controller": mode == "closed_loop",
        "uses_sine_carrier": mode == "closed_loop",
        "controller_is_average_model": False,
    }

    layout = ClosedLoopLayout(
        variant=variant,
        mode=mode,
        nodes=nodes,
        elements=elements,
        branches=branches,
        features=features,
        controller=controller_layout,
        load=load_layout,
        line=line_layout,
        title=circuit_title,
    )
    return circuit, layout


__all__ = [
    "ClosedLoopLayout",
    "NODE_INPUT",
    "NODE_OUTPUT",
    "NODE_SWITCH",
    "build_closed_loop_buck",
]

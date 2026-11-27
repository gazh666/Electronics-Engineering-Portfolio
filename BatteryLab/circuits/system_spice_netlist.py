"""同网表联合仿真电路：3S 电池 ECM + 保护通路 + Buck 功率级 + 实际闭环反馈。

与 PowerLab 的关系（必须如实说明）：

- 功率级拓扑、器件参数、控制器表达式来自 PowerLab 第七阶段真实闭环网表
  （``circuits/closed_loop_buck.py``、``control/spice_controller.py``）；
- 由于 PowerLab 构建器把输入源硬编码为理想电压源，无法直接接入电池端口，
  本模块在 BatteryLab 内按同一表达式重建电路，并把输入源替换为真实电池 ECM；
- MOSFET 与二极管仍是 PowerLab 的**教学模型**（Level 1 NMOS / 非理想二极管），
  不是商业器件模型；
- 电池电压由功率级输入电流在 ECM 上产生压降，属于真实双向物理反馈。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from PySpice.Spice.Netlist import Circuit

GND = "0"
TWO_PI = 6.283185307179586


@dataclass
class IntegratedLayout:
    nodes: dict[str, str]
    branches: dict[str, str]
    features: dict[str, Any] = field(default_factory=dict)
    model_sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": dict(self.nodes),
            "branches": dict(self.branches),
            "features": dict(self.features),
            "model_sources": dict(self.model_sources),
        }


def _soft_start_points(target_v: float, duration_s: float, end_time_s: float) -> list[tuple[float, float]]:
    # 软启动必须完整落在仿真窗口内，否则 PWL 时间点非递增。
    effective = min(max(duration_s, 0.0), end_time_s * 0.9)
    if effective <= 0:
        return [(0.0, target_v), (end_time_s, target_v)]
    return [(0.0, 0.0), (effective, target_v), (end_time_s, target_v)]


def add_cell_stack(circuit: Circuit, cells: Sequence[dict[str, float]], prefix: str = "C") -> dict[str, Any]:
    """把 3 节独立 1RC ECM 串成电池组，返回节点映射。"""
    if not cells:
        raise ValueError("至少需要一节电芯")
    taps = [GND]
    for index, cell in enumerate(cells, start=1):
        negative = taps[-1]
        positive = f"tp{index}"
        o = f"{prefix}{index}_o"
        x = f"{prefix}{index}_x"
        circuit.V(f"OCV{index}", o, negative, float(cell["ocv_v"]))
        circuit.R(f"RP{index}", o, x, float(cell["rp_ohm"]))
        circuit.C(f"CP{index}", o, x, float(cell["cp_f"]), ic=float(cell.get("initial_polarization_v", 0.0)))
        circuit.R(f"R0_{index}", x, positive, float(cell["r0_ohm"]))
        taps.append(positive)
    return {"taps": taps, "battery_positive": taps[-1]}


def add_protection_path(
    circuit: Circuit,
    *,
    input_node: str,
    output_node: str,
    path_resistance_ohm: float,
    control_points: Sequence[tuple[float, float]] | None,
    off_resistance_ohm: float = 1e6,
    end_time_s: float,
) -> dict[str, Any]:
    """受控保护通路：导通电阻 = 第五阶段通路电阻，关断 = 高阻。"""
    points = list(control_points) if control_points else [(0.0, 1.0), (end_time_s, 1.0)]
    if any(point[0] < 0 or point[0] > end_time_s for point in points):
        raise ValueError("保护控制时刻必须位于仿真窗口内")
    if any(later[0] < earlier[0] for earlier, later in zip(points, points[1:])):
        raise ValueError("保护控制时刻必须非递减")
    if points[0][0] > 0:
        points.insert(0, (0.0, points[0][1]))
    if points[-1][0] < end_time_s:
        points.append((end_time_s, points[-1][1]))
    circuit.PieceWiseLinearVoltageSource("PCTRL", "prot_ctrl", circuit.gnd, values=points)
    expression = (
        f"V({input_node},{output_node})/"
        f"({path_resistance_ohm:.12g}+({off_resistance_ohm:.12g}-{path_resistance_ohm:.12g})"
        f"*(1-min(max(V(prot_ctrl),0),1)))"
    )
    circuit.B("BPROT", input_node, output_node, current_expression=expression)
    return {
        "control_points": points,
        "on_resistance_ohm": path_resistance_ohm,
        "off_resistance_ohm": off_resistance_ohm,
        "expression": expression,
    }


def add_buck_power_stage(
    circuit: Circuit,
    *,
    input_node: str,
    inductance_h: float,
    inductor_dcr_ohm: float,
    capacitance_f: float,
    capacitor_esr_ohm: float,
    load_resistance_ohm: float,
    switch_on_resistance_ohm: float = 1e-3,
    switch_off_resistance_ohm: float = 1e6,
    switch_threshold_v: float = 2.5,
    switch_hysteresis_v: float = 0.1,
    diode_saturation_a: float = 1e-6,
    diode_series_ohm: float = 1e-3,
) -> dict[str, str]:
    """PowerLab 同拓扑功率级（SW 开关模型 + 教学二极管）。

    这里使用 PowerLab 自带的 ``SWMOD`` 电压控制开关模型（RON=1 mΩ），
    与 PowerLab ``nonideal_buck.py`` 的 LEGACY_SWITCH 完全一致；它**不是**
    商业 MOSFET 模型，也不包含真实栅极电荷与开关损耗。
    """
    circuit.V("DSENSE", input_node, "drain", 0.0)
    circuit.model(
        "SWMOD",
        "SW",
        RON=switch_on_resistance_ohm,
        ROFF=switch_off_resistance_ohm,
        VT=switch_threshold_v,
        VH=switch_hysteresis_v,
    )
    circuit.S("1", "drain", "sw", "gate", circuit.gnd, model="SWMOD")

    circuit.V("DIOSENSE", circuit.gnd, "diode_a", 0.0)
    circuit.model(
        "DFREE",
        "d",
        IS=diode_saturation_a,
        N=1.0,
        RS=diode_series_ohm,
        CJO=2e-10,
        VJ=0.7,
        M=0.5,
        TT=0.0,
    )
    circuit.D("FREE", "diode_a", "sw", model="DFREE")

    circuit.V("LSENSE", "sw", "lx", 0.0)
    circuit.L("1", "lx", "l_dcr", inductance_h)
    circuit.R("RDCR", "l_dcr", "out", inductor_dcr_ohm)

    circuit.V("CSENSE", "out", "c_esr", 0.0)
    circuit.C("1", "c_esr", "cap_internal", capacitance_f)
    circuit.R("RESR", "cap_internal", circuit.gnd, capacitor_esr_ohm)

    circuit.V("LOADSENSE", "out", "load_node", 0.0)
    circuit.R("RLOAD", "load_node", circuit.gnd, load_resistance_ohm)
    return {
        "main_switch": "S1",
        "switch_model": "SWMOD",
        "freewheel_diode": "DFREE",
        "inductor": "L1",
        "inductor_dcr": "RDCR",
        "output_capacitor": "C1",
        "capacitor_esr": "RESR",
        "load": "RLOAD",
    }


def add_behavioral_pi(
    circuit: Circuit,
    *,
    output_node: str,
    input_node: str,
    target_v: float,
    kp: float,
    ki: float,
    duty_min: float,
    duty_max: float,
    tracking_gain: float = 2000.0,
    soft_start_s: float = 2e-3,
    switching_frequency_hz: float = 100e3,
    end_time_s: float,
    vin_min_for_feedforward_v: float = 2.0,
    smoothing_width: float = 0.1,
    gate_drive_voltage_v: float = 5.0,
) -> dict[str, str]:
    """与 PowerLab ``add_behavioral_pi_controller`` 相同的表达式集合。"""
    circuit.PieceWiseLinearVoltageSource(
        "CREF", "ref", circuit.gnd, values=_soft_start_points(target_v, soft_start_s, end_time_s)
    )
    circuit.B("CERR", "err", circuit.gnd, voltage_expression=f"V(ref)-V({output_node})")
    circuit.B(
        "CFF",
        "ff",
        circuit.gnd,
        voltage_expression=f"V(ref)/max(V({input_node}),{vin_min_for_feedforward_v:.12g})",
    )
    circuit.B("CPROP", "prop", circuit.gnd, voltage_expression=f"{kp:.12g}*V(err)")
    circuit.B("CRAW", "raw", circuit.gnd, voltage_expression="V(ff)+V(prop)+V(integ)")
    circuit.B(
        "CLIM",
        "duty",
        circuit.gnd,
        voltage_expression=f"min(max(V(raw),{duty_min:.12g}),{duty_max:.12g})",
    )
    circuit.C("CINT", "integ", circuit.gnd, 1.0, ic=0)
    circuit.B(
        "CIINT",
        circuit.gnd,
        "integ",
        current_expression=(
            f"{ki:.12g}*V(err)+{tracking_gain:.12g}*(V(duty)-V(raw))"
        ),
    )
    circuit.R("CILEAK", "integ", circuit.gnd, 1e9)
    circuit.B(
        "CRAMP",
        "ramp",
        circuit.gnd,
        voltage_expression=f"0.5*(1+sin({TWO_PI * switching_frequency_hz:.12g}*time))",
    )
    circuit.B(
        "CPWM",
        "pwm",
        circuit.gnd,
        voltage_expression=(
            f"min(max((V(duty)-V(ramp))/{smoothing_width:.12g}+0.5,0),1)"
        ),
    )
    circuit.B(
        "CDRV",
        "gdrv",
        circuit.gnd,
        voltage_expression=f"{gate_drive_voltage_v:.12g}*V(pwm)",
    )
    circuit.R("RCG", "gdrv", "gate", 10.0)
    circuit.R("RCGS", "gate", circuit.gnd, 100e3)
    circuit.C("CGATE", "gate", circuit.gnd, 1e-9)
    return {
        "reference": "VCREF",
        "error": "BCERR",
        "duty_node": "duty",
        "pwm_node": "pwm",
        "integrator": "CINT",
    }


def build_integrated_system(
    cells: Sequence[dict[str, float]],
    *,
    path_resistance_ohm: float = 0.052,
    input_capacitance_f: float = 100e-6,
    input_capacitor_ic_v: float = 10.5,
    inductance_h: float = 47e-6,
    inductor_dcr_ohm: float = 0.05,
    capacitance_f: float = 100e-6,
    capacitor_esr_ohm: float = 0.03,
    load_resistance_ohm: float = 2.5,
    target_output_voltage_v: float = 5.0,
    switching_frequency_hz: float = 100e3,
    kp: float = 0.0585,
    ki: float = 117.66,
    duty_min: float = 0.02,
    duty_max: float = 0.90,
    soft_start_s: float = 2e-3,
    protection_control_points: Sequence[tuple[float, float]] | None = None,
    end_time_s: float = 0.010,
    title: str = "BatteryLab stage-9 integrated battery + closed-loop buck",
) -> tuple[Circuit, IntegratedLayout]:
    if end_time_s <= 0:
        raise ValueError("end_time_s 必须为正")
    if load_resistance_ohm <= 0:
        raise ValueError("负载电阻必须为正")
    circuit = Circuit(title)

    stack = add_cell_stack(circuit, cells)
    bpos = stack["battery_positive"]
    circuit.V("BSENSE", bpos, "prot_in", 0.0)
    protection = add_protection_path(
        circuit,
        input_node="prot_in",
        output_node="vin",
        path_resistance_ohm=path_resistance_ohm,
        control_points=protection_control_points,
        end_time_s=end_time_s,
    )
    circuit.C("CIN", "vin", circuit.gnd, input_capacitance_f, ic=input_capacitor_ic_v)
    stage = add_buck_power_stage(
        circuit,
        input_node="vin",
        inductance_h=inductance_h,
        inductor_dcr_ohm=inductor_dcr_ohm,
        capacitance_f=capacitance_f,
        capacitor_esr_ohm=capacitor_esr_ohm,
        load_resistance_ohm=load_resistance_ohm,
    )
    controller = add_behavioral_pi(
        circuit,
        output_node="out",
        input_node="vin",
        target_v=target_output_voltage_v,
        kp=kp,
        ki=ki,
        duty_min=duty_min,
        duty_max=duty_max,
        soft_start_s=soft_start_s,
        switching_frequency_hz=switching_frequency_hz,
        end_time_s=end_time_s,
    )

    layout = IntegratedLayout(
        nodes={
            "battery_positive": bpos,
            "protection_input": "prot_in",
            "converter_input": "vin",
            "switch": "sw",
            "output": "out",
            "duty": "duty",
            "pwm": "pwm",
        },
        branches={
            "battery_current": "bsense",
            "converter_input_current": "vdsense",
            "inductor_current": "vlsense",
            "load_current": "vloadsense",
        },
        features={
            "battery_ecm_in_netlist": True,
            "battery_voltage_depends_on_load": True,
            "closed_loop_feedback": True,
            "switching_level": True,
            "protection_switch_is_behavioral": True,
            "mosfet_is_educational_level1": True,
        },
        model_sources={
            "battery_model_source": "stage3_identified_first_order_rc_ecm",
            "power_stage_model_source": "powerlab_legacy_sw_model_ron_1mohm_reproduced",
            "controller_source": "powerlab_stage7_behavioral_pi_expressions_reproduced",
            "protection_model_source": "stage5_path_resistance_with_behavioral_switch",
        },
    )
    return circuit, layout


def save_netlist(circuit: Circuit, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(circuit), encoding="utf-8")
    return target


__all__ = [
    "IntegratedLayout",
    "add_behavioral_pi",
    "add_buck_power_stage",
    "add_cell_stack",
    "add_protection_path",
    "build_integrated_system",
    "save_netlist",
]

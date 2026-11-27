"""Buck 充电功率级（开环）：真实 ngspice 网表与电池夹具。

电池夹具使用第三阶段冻结辨识参数，按三节独立建模，便于读取每节端电压
供第五阶段保护控制器使用。开环结果只作为闭环对照基线，不代表充电控制性能。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit

from charging.battery_adapter import load_identified_battery_bundle
from charging.config import PowerStageConfig
from circuits.charger_switch_models import (
    ChargerDeviceModels,
    add_device_models,
)
from circuits.spice_utils import run_transient, save_netlist


class ChargerCircuitError(RuntimeError):
    """充电电路构建或求解失败。"""


@dataclass(frozen=True)
class CellFixture:
    ocv_v: float
    r0_ohm: float
    r1_ohm: float
    c1_f: float
    soc: float

    def __post_init__(self) -> None:
        for name in ("ocv_v", "r0_ohm", "r1_ohm", "c1_f", "soc"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ChargerCircuitError(f"电芯夹具参数非法: {name}")
        if self.c1_f <= 0.0:
            raise ChargerCircuitError("极化电容必须为正")

    def to_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class PackFixture:
    cells: tuple[CellFixture, ...]
    path_resistance_ohm: float
    model_id: str
    source_note: str = "identified_frozen_parameters"

    def __post_init__(self) -> None:
        if len(self.cells) < 1:
            raise ChargerCircuitError("至少需要一节电芯")
        if not math.isfinite(self.path_resistance_ohm) or self.path_resistance_ohm < 0.0:
            raise ChargerCircuitError("充电通路电阻非法")

    @classmethod
    def from_identified(
        cls,
        socs: Sequence[float],
        path_resistance_ohm: float,
        model_id: str | None = None,
    ) -> "PackFixture":
        bundle = load_identified_battery_bundle(model_id)
        parameters = bundle["parameters"]
        ocv_model = bundle["ocv_model"]
        cells = tuple(
            CellFixture(
                ocv_v=float(ocv_model.voltage(float(soc))),
                r0_ohm=float(parameters.r0_ohm),
                r1_ohm=float(parameters.r1_ohm),
                c1_f=float(parameters.c1_f),
                soc=float(soc),
            )
            for soc in socs
        )
        return cls(
            cells=cells,
            path_resistance_ohm=float(path_resistance_ohm),
            model_id=str(bundle["model_id"]),
        )

    @classmethod
    def from_equivalent_voltage(
        cls,
        pack_ocv_v: float,
        path_resistance_ohm: float,
        series_cells: int = 3,
        model_id: str | None = None,
    ) -> "PackFixture":
        """局部线性化夹具：给定电池组等效开路电压，内阻/极化仍取辨识参数。

        开关级短时实验（8–12 ms）不求解 SOC，因此 OCV 被固定；SOC 字段只是由
        OCV 表反查的近似值，不得当作充电进度。
        """
        if series_cells < 1:
            raise ChargerCircuitError("串联节数至少为 1")
        bundle = load_identified_battery_bundle(model_id)
        parameters = bundle["parameters"]
        ocv_model = bundle["ocv_model"]
        per_cell = float(pack_ocv_v) / series_cells
        soc_estimates = np.interp(
            per_cell,
            np.asarray(ocv_model.ocv_table, dtype=float),
            np.asarray(ocv_model.soc_table, dtype=float),
        )
        cells = tuple(
            CellFixture(
                ocv_v=per_cell,
                r0_ohm=float(parameters.r0_ohm),
                r1_ohm=float(parameters.r1_ohm),
                c1_f=float(parameters.c1_f),
                soc=float(soc_estimates),
            )
            for _ in range(series_cells)
        )
        return cls(
            cells=cells,
            path_resistance_ohm=float(path_resistance_ohm),
            model_id=str(bundle["model_id"]),
            source_note="local_equivalent_voltage_fixture_not_soc_resolved",
        )

    @property
    def pack_ocv_v(self) -> float:
        return float(sum(cell.ocv_v for cell in self.cells))

    @property
    def pack_r0_ohm(self) -> float:
        return float(sum(cell.r0_ohm for cell in self.cells))

    def to_dict(self) -> dict[str, Any]:
        return {
            "cells": [cell.to_dict() for cell in self.cells],
            "path_resistance_ohm": self.path_resistance_ohm,
            "pack_ocv_v": self.pack_ocv_v,
            "pack_r0_ohm": self.pack_r0_ohm,
            "model_id": self.model_id,
            "source_note": self.source_note,
        }


@dataclass(frozen=True)
class ChargerLayout:
    nodes: dict[str, str]
    branches: dict[str, str]
    cell_positive_nodes: tuple[str, ...]
    cell_negative_nodes: tuple[str, ...]
    model_names: tuple[str, str]
    features: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": dict(self.nodes),
            "branches": dict(self.branches),
            "cell_positive_nodes": list(self.cell_positive_nodes),
            "cell_negative_nodes": list(self.cell_negative_nodes),
            "model_names": list(self.model_names),
            "features": dict(self.features),
        }


def add_power_stage(
    circuit: Circuit,
    power_stage: PowerStageConfig,
    fixture: PackFixture,
    models: ChargerDeviceModels,
    *,
    vin_expression: str = "DC 18",
    suffix: str = "",
) -> ChargerLayout:
    """把输入源、开关、二极管、LC、输出电容与 3S 电池夹具写入网表。"""
    switch_model, diode_model = add_device_models(circuit, models, suffix=suffix)

    nodes = {
        "vin": "vin",
        "sw": "sw",
        "lx": "lx",
        "ldcr": "ldcr",
        "out": "out",
        "cap": "cap",
        "path": "path",
        "pack": "pack",
    }
    terminal_nodes = ["pack"] + [f"t{index}" for index in range(1, len(fixture.cells))]
    cell_positive = tuple(terminal_nodes)
    cell_negative = tuple(terminal_nodes[1:] + ["0"])

    lines = [
        f"VIN {nodes['vin']} 0 {vin_expression}",
        f"SMAIN {nodes['vin']} {nodes['sw']} gate 0 {switch_model}",
        f"DFREE 0 {nodes['sw']} {diode_model}",
        f"VSENSE {nodes['sw']} {nodes['lx']} 0",
        f"L1 {nodes['lx']} {nodes['ldcr']} {power_stage.inductance_h:.9g}",
        f"RL {nodes['ldcr']} {nodes['out']} {power_stage.inductor_dcr_ohm:.9g}",
        f"RESR {nodes['out']} {nodes['cap']} {power_stage.capacitor_esr_ohm:.9g}",
        f"COUT {nodes['cap']} 0 {power_stage.capacitance_f:.9g}",
        f"VBATSENSE {nodes['out']} {nodes['path']} 0",
        f"RPATH {nodes['path']} {nodes['pack']} {fixture.path_resistance_ohm:.9g}",
        # 开关节点缓冲，抑制理想开关造成的数值尖峰。
        f"C_SW {nodes['sw']} 0 1n",
    ]

    for index, (cell, top, bottom) in enumerate(
        zip(fixture.cells, cell_positive, cell_negative), start=1
    ):
        a = f"a{index}"
        o = f"o{index}"
        lines.extend(
            [
                f"R0_{index} {top} {a} {cell.r0_ohm:.9g}",
                f"R1_{index} {a} {o} {cell.r1_ohm:.9g}",
                f"C1_{index} {a} {o} {cell.c1_f:.9g}",
                f"VOCV_{index} {o} {bottom} DC {cell.ocv_v:.9g}",
            ]
        )

    circuit.raw_spice += "\n".join(lines) + "\n"

    return ChargerLayout(
        nodes=nodes,
        branches={"input": "VIN", "inductor": "VSENSE", "battery": "VBATSENSE"},
        cell_positive_nodes=cell_positive,
        cell_negative_nodes=cell_negative,
        model_names=(switch_model, diode_model),
        features={
            "topology": "asynchronous_buck",
            "battery_model": "3s_identified_first_order_rc",
            "path_resistance_ohm": fixture.path_resistance_ohm,
        },
    )


def step_expression(
    initial: float,
    final: float | None = None,
    step_time_s: float | None = None,
    rise_time_s: float = 10e-6,
) -> str:
    """构造恒定或单次阶跃的 SPICE 源表达式（有限转换时间）。"""
    if final is None or step_time_s is None:
        return f"DC {float(initial):.9g}"
    if step_time_s < 0.0 or rise_time_s <= 0.0:
        raise ChargerCircuitError("阶跃时间或转换时间非法")
    return (
        f"PWL(0 {float(initial):.9g} {float(step_time_s):.9g} {float(initial):.9g} "
        f"{float(step_time_s) + float(rise_time_s):.9g} {float(final):.9g})"
    )


def pwl_expression(points: Sequence[tuple[float, float]]) -> str:
    if len(points) < 2:
        raise ChargerCircuitError("PWL 至少需要两个点")
    body = " ".join(f"{float(t):.9g} {float(v):.9g}" for t, v in points)
    return f"PWL({body})"


def build_open_loop_circuit(
    power_stage: PowerStageConfig,
    fixture: PackFixture,
    *,
    duty: float,
    models: ChargerDeviceModels | None = None,
    vin_expression: str = "DC 18",
    title: str = "BatteryLab stage6 open-loop buck charger",
) -> tuple[Circuit, ChargerLayout]:
    if not 0.0 <= duty < 1.0:
        raise ChargerCircuitError("占空比必须在 [0, 1) 内")
    devices = models or ChargerDeviceModels.from_power_stage(power_stage)
    circuit = Circuit(title)
    layout = add_power_stage(
        circuit, power_stage, fixture, devices, vin_expression=vin_expression
    )

    controller = [
        f".param FS={power_stage.switching_frequency_hz:.9g}",
        f"VDUTY duty 0 DC {duty:.9g}",
        "BRAMP ramp 0 V={time*FS-floor(time*FS)}",
        "BGATE graw 0 V={5*u(V(duty)-V(ramp))*u(time-1e-9)}",
        "RG graw gate 100",
        "CG gate 0 1n",
    ]
    circuit.raw_spice += "\n".join(controller) + "\n"
    return circuit, layout


@dataclass(frozen=True)
class ChargerWaveform:
    time_s: np.ndarray
    inductor_current_a: np.ndarray
    charging_current_a: np.ndarray
    ecm_current_a: np.ndarray
    output_voltage_v: np.ndarray
    pack_voltage_v: np.ndarray
    input_voltage_v: np.ndarray
    input_current_a: np.ndarray
    cell_voltages_v: tuple[np.ndarray, ...]
    duty_command: np.ndarray
    gate_voltage_v: np.ndarray
    current_reference_a: np.ndarray | None = None

    def to_columns(self) -> dict[str, np.ndarray]:
        return {
            "time_s": self.time_s,
            "inductor_current_a": self.inductor_current_a,
            "charging_current_a": self.charging_current_a,
            "ecm_current_a": self.ecm_current_a,
            "charger_output_voltage_v": self.output_voltage_v,
            "battery_pack_voltage_v": self.pack_voltage_v,
            "input_voltage_v": self.input_voltage_v,
            "input_current_a": self.input_current_a,
            "duty": self.duty_command,
            "current_reference_a": self.current_reference_a,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "points": int(self.time_s.size),
            "duration_s": float(self.time_s[-1] - self.time_s[0]),
            "final_pack_voltage_v": float(self.pack_voltage_v[-1]),
            "final_charging_current_a": float(self.charging_current_a[-1]),
            "peak_charging_current_a": float(self.charging_current_a.max()),
            "peak_pack_voltage_v": float(self.pack_voltage_v.max()),
        }


def _branch(data: dict[str, np.ndarray], name: str) -> np.ndarray:
    key = f"I:{name.lower()}"
    if key not in data:
        raise ChargerCircuitError(f"缺少支路电流: {key}")
    return np.asarray(data[key], dtype=float)


def _node(data: dict[str, np.ndarray], name: str) -> np.ndarray:
    if name not in data:
        raise ChargerCircuitError(f"缺少节点电压: {name}")
    return np.asarray(data[name], dtype=float)


def extract_waveform(
    data: dict[str, np.ndarray],
    layout: ChargerLayout,
    *,
    current_reference_node: str | None = None,
) -> ChargerWaveform:
    time = _node(data, "time_s")
    battery_current = _branch(data, layout.branches["battery"])
    inductor_current = _branch(data, layout.branches["inductor"])
    input_current = -_branch(data, layout.branches["input"])
    cell_voltages = tuple(
        _node(data, positive) - (0.0 if negative == "0" else _node(data, negative))
        for positive, negative in zip(layout.cell_positive_nodes, layout.cell_negative_nodes)
    )
    return ChargerWaveform(
        time_s=time,
        inductor_current_a=inductor_current,
        charging_current_a=battery_current,
        ecm_current_a=-battery_current,
        output_voltage_v=_node(data, layout.nodes["out"]),
        pack_voltage_v=_node(data, layout.nodes["pack"]),
        input_voltage_v=_node(data, layout.nodes["vin"]),
        input_current_a=input_current,
        cell_voltages_v=cell_voltages,
        duty_command=_node(data, "duty"),
        gate_voltage_v=_node(data, "gate"),
        current_reference_a=_node(data, current_reference_node)
        if current_reference_node is not None
        else None,
    )


def run_open_loop_buck(
    power_stage: PowerStageConfig,
    fixture: PackFixture,
    *,
    duty: float,
    duration_s: float,
    step_s: float,
    vin_expression: str = "DC 18",
    temperature_c: float = 25.0,
    reltol: float = 1e-3,
    abstol: float = 1e-8,
    vntol: float = 1e-5,
) -> tuple[ChargerWaveform, Circuit, ChargerLayout]:
    circuit, layout = build_open_loop_circuit(
        power_stage, fixture, duty=duty, vin_expression=vin_expression
    )
    nodes = (
        "vin",
        "sw",
        "lx",
        "ldcr",
        "out",
        "cap",
        "path",
        "pack",
        "duty",
        "gate",
    ) + layout.cell_positive_nodes[1:] + tuple(
        f"a{index}" for index in range(1, len(fixture.cells) + 1)
    ) + tuple(f"o{index}" for index in range(1, len(fixture.cells) + 1))
    data = run_transient(
        circuit,
        duration_s=duration_s,
        step_s=step_s,
        max_step_s=min(step_s, 1.0 / (20.0 * power_stage.switching_frequency_hz)),
        nodes=nodes,
        branches=("VIN", "VSENSE", "VBATSENSE"),
        temperature_c=temperature_c,
        reltol=reltol,
        abstol=abstol,
        vntol=vntol,
    )
    return extract_waveform(data, layout), circuit, layout


def persist_netlist(circuit: Circuit, path: Any) -> Any:
    return save_netlist(circuit, path)

"""真实 ngspice 3S1P 电池组电路。

三节 ECM 首尾串联，提取单体差分电压：
Vcell1 = V(cell1) - 0，Vcell2 = V(cell2) - V(cell1)，Vcell3 = V(pack) - V(cell2)。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit

from battery_models.parameters import RCBranch
from circuits.battery_ecm_circuit import (
    SpiceCircuitError,
    build_pwl_points,
    pwl_current,
    run_transient,
)
from simulations.load_profiles import LoadProfile


def build_pack_circuit(
    branches: Sequence[RCBranch],
    r0_ohm: float,
    ocv_v: float,
    profile: LoadProfile,
    *,
    cells: int = 3,
    transition_s: float = 0.001,
) -> Circuit:
    """构造真实三串电池组网表（每节包含 R0 与两个 RC 支路）。"""
    if cells < 1:
        raise SpiceCircuitError("电芯数量必须至少为 1")
    if len(branches) != 2:
        raise SpiceCircuitError("电池组电路要求每节包含两个 RC 支路")
    if transition_s <= 0:
        raise SpiceCircuitError("电流转换时间必须为正")
    points = build_pwl_points(profile, transition_s)
    circuit = Circuit(f"BatteryLab {cells}S1P pack")
    previous_node = circuit.gnd
    for index in range(1, cells + 1):
        stage = f"cell{index}"
        node_a = f"{stage}_a"
        node_b = f"{stage}_b"
        circuit.V(f"OCV{index}", f"{stage}_ocv", previous_node, float(ocv_v))
        circuit.R(f"0_{index}", f"{stage}_ocv", node_a, r0_ohm)
        circuit.R(f"1_{index}", node_a, node_b, branches[0].resistance_ohm)
        circuit.C(f"1_{index}", node_a, node_b, branches[0].capacitance_f)
        circuit.R(f"2_{index}", node_b, stage, branches[1].resistance_ohm)
        circuit.C(f"2_{index}", node_b, stage, branches[1].capacitance_f)
        previous_node = stage
    circuit.PieceWiseLinearCurrentSource("LOAD", f"cell{cells}", circuit.gnd, values=points)
    return circuit


def extract_pack_waveform(
    data: dict[str, np.ndarray],
    points: Sequence[tuple[float, float]],
    *,
    cells: int = 3,
) -> dict[str, np.ndarray]:
    time = data["time_s"]
    waveform: dict[str, np.ndarray] = {
        "time_s": time,
        "current_a": pwl_current(time, points),
    }
    previous = np.zeros_like(time)
    differentials = []
    for index in range(1, cells + 1):
        node = f"cell{index}"
        if node not in data:
            raise SpiceCircuitError(f"求解结果缺少节点: {node}")
        differential = data[node] - previous
        waveform[f"cell{index}_voltage_v"] = differential
        differentials.append(differential)
        previous = data[node]
    waveform["pack_voltage_v"] = data[f"cell{cells}"]
    waveform["sum_cell_voltage_v"] = np.sum(np.vstack(differentials), axis=0)
    return waveform


def build_and_run_pack(
    branches: Sequence[RCBranch],
    r0_ohm: float,
    ocv_v: float,
    profile: LoadProfile,
    *,
    cells: int = 3,
    step_s: float = 0.05,
    transition_s: float = 0.001,
) -> tuple[Circuit, dict[str, Any]]:
    circuit = build_pack_circuit(branches, r0_ohm, ocv_v, profile, cells=cells, transition_s=transition_s)
    nodes = tuple(f"cell{index}" for index in range(1, cells + 1))
    data = run_transient(circuit, duration_s=profile.duration_s, step_s=step_s, nodes=nodes)
    points = build_pwl_points(profile, transition_s)
    waveform = extract_pack_waveform(data, points, cells=cells)
    return circuit, {
        "waveform": waveform,
        "pwl_points": points,
        "cells": cells,
        "duration_s": profile.duration_s,
        "step_s": step_s,
        "transition_s": transition_s,
    }

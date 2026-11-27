"""真实 ngspice 单体电池等效电路。

使用 PySpice 构造网表并调用真实 ngspice 瞬态求解，不把 Python 预生成电压
作为 SPICE 输出源。参考网表采用 1 ms 有限电流转换时间。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit

from battery_models.parameters import CellParameters, RCBranch
from simulations.load_profiles import LoadProfile


class SpiceCircuitError(RuntimeError):
    """真实 SPICE 求解失败。"""


def build_pwl_points(profile: LoadProfile, transition_s: float = 0.001) -> list[tuple[float, float]]:
    """把分段恒流工况转换为 PWL 点列，电流变化使用有限转换时间。"""
    if transition_s <= 0:
        raise SpiceCircuitError("电流转换时间必须为正")
    points: list[tuple[float, float]] = [(0.0, profile.segments[0].current_a)]
    elapsed = 0.0
    for index, segment in enumerate(profile.segments):
        elapsed += segment.duration_s
        if index + 1 < len(profile.segments):
            next_current = profile.segments[index + 1].current_a
            if abs(next_current - segment.current_a) > 1e-12:
                points.append((elapsed, segment.current_a))
                points.append((elapsed + transition_s, next_current))
    points.append((profile.duration_s, profile.segments[-1].current_a))
    return points


def pwl_current(time_s: Sequence[float], points: Sequence[tuple[float, float]]) -> np.ndarray:
    times = np.asarray(time_s, dtype=float)
    point_times = np.array([point[0] for point in points], dtype=float)
    point_values = np.array([point[1] for point in points], dtype=float)
    return np.interp(times, point_times, point_values)


def build_ecm_circuit(
    model_name: str,
    parameters: CellParameters,
    branches: Sequence[RCBranch],
    ocv_v: float,
    profile: LoadProfile,
    *,
    transition_s: float = 0.001,
) -> Circuit:
    """构造 Rint / 一阶 RC / 二阶 RC 的真实电路网表。"""
    points = build_pwl_points(profile, transition_s)
    circuit = Circuit(f"BatteryLab {model_name} benchmark")
    circuit.V("OCV", "n_ocv", circuit.gnd, float(ocv_v))
    if model_name == "rint":
        circuit.R("0", "n_ocv", "out", parameters.r0_ohm)
        output_node = "out"
    elif model_name == "first_order_rc":
        circuit.R("0", "n_ocv", "n1", parameters.r0_ohm)
        circuit.R("1", "n1", "out", branches[0].resistance_ohm)
        circuit.C("1", "n1", "out", branches[0].capacitance_f)
        output_node = "out"
    elif model_name == "second_order_rc":
        circuit.R("0", "n_ocv", "n1", parameters.r0_ohm)
        circuit.R("1", "n1", "n2", branches[0].resistance_ohm)
        circuit.C("1", "n1", "n2", branches[0].capacitance_f)
        circuit.R("2", "n2", "out", branches[1].resistance_ohm)
        circuit.C("2", "n2", "out", branches[1].capacitance_f)
        output_node = "out"
    else:
        raise SpiceCircuitError(f"不支持的模型: {model_name!r}")
    circuit.PieceWiseLinearCurrentSource("LOAD", output_node, circuit.gnd, values=points)
    return circuit


def run_transient(
    circuit: Circuit,
    *,
    duration_s: float,
    step_s: float,
    reltol: float = 1e-5,
    abstol: float = 1e-10,
    vntol: float = 1e-7,
    nodes: Sequence[str] = ("out", "n1", "n2"),
) -> dict[str, np.ndarray]:
    """执行真实 ngspice 瞬态求解。

    ngspice 对三串高容值 RC 网络在 reltol=1e-6 时可能报 timestep too small，
    因此默认采用 1e-5 / 1e-7 / 1e-10，并在结果中记录实际设置。
    """
    if duration_s <= 0 or step_s <= 0:
        raise SpiceCircuitError("仿真时长与步长必须为正")
    try:
        simulator = circuit.simulator(temperature=25, nominal_temperature=25)
        simulator.options(reltol=reltol, abstol=abstol, vntol=vntol)
        analysis = simulator.transient(step_time=step_s, end_time=duration_s, start_time=0, max_time=step_s)
    except Exception as exc:  # noqa: BLE001 - 必须保留真实求解失败原因
        raise SpiceCircuitError(f"ngspice 瞬态求解失败: {type(exc).__name__}: {exc}") from exc

    data: dict[str, np.ndarray] = {"time_s": np.asarray(analysis.time, dtype=float)}
    for node in nodes:
        try:
            data[node] = np.asarray(analysis[node], dtype=float)
        except Exception:  # noqa: BLE001 - 节点不存在属正常情况
            continue
    if "out" not in data and "cell1" not in data:
        raise SpiceCircuitError("求解结果缺少输出节点电压")
    if not np.isfinite(data["time_s"]).all():
        raise SpiceCircuitError("求解结果含有非有限数值")
    return data


def extract_cell_waveform(
    model_name: str,
    data: dict[str, np.ndarray],
    points: Sequence[tuple[float, float]],
) -> dict[str, np.ndarray]:
    out = data["out"]
    current = pwl_current(data["time_s"], points)
    waveform: dict[str, np.ndarray] = {
        "time_s": data["time_s"],
        "current_a": current,
        "terminal_voltage_v": out,
    }
    if model_name == "first_order_rc" and "n1" in data:
        waveform["polarization_1_v"] = data["n1"] - out
    if model_name == "second_order_rc" and "n1" in data and "n2" in data:
        waveform["polarization_1_v"] = data["n1"] - data["n2"]
        waveform["polarization_2_v"] = data["n2"] - out
    return waveform


def save_netlist(circuit: Circuit, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(circuit), encoding="utf-8")
    return path


def build_and_run_single_cell(
    model_name: str,
    parameters: CellParameters,
    branches: Sequence[RCBranch],
    ocv_v: float,
    profile: LoadProfile,
    *,
    step_s: float = 0.05,
    transition_s: float = 0.001,
) -> tuple[Circuit, dict[str, Any]]:
    circuit = build_ecm_circuit(model_name, parameters, branches, ocv_v, profile, transition_s=transition_s)
    data = run_transient(circuit, duration_s=profile.duration_s, step_s=step_s)
    points = build_pwl_points(profile, transition_s)
    waveform = extract_cell_waveform(model_name, data, points)
    return circuit, {
        "waveform": waveform,
        "pwl_points": points,
        "duration_s": profile.duration_s,
        "step_s": step_s,
        "transition_s": transition_s,
        "nodes": sorted(key for key in data if key != "time_s"),
    }

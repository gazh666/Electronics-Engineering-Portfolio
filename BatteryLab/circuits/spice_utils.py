"""真实 ngspice 求解通用封装（工作点/瞬态/交流小信号）。

所有结果均来自 PySpice 调用真实 ngspice 后端，不在此处生成任何"电路输出"。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit


class SpiceRunError(RuntimeError):
    """真实 SPICE 求解失败。"""


_SOLVE_COUNTER = {"count": 0}


def reset_solve_counter() -> None:
    _SOLVE_COUNTER["count"] = 0


def get_solve_count() -> int:
    return int(_SOLVE_COUNTER["count"])


def _count_solve() -> None:
    _SOLVE_COUNTER["count"] += 1


def _simulator(circuit: Circuit, temperature_c: float = 25.0):
    try:
        return circuit.simulator(temperature=temperature_c, nominal_temperature=temperature_c)
    except Exception as exc:  # noqa: BLE001 - 保留真实失败原因
        raise SpiceRunError(f"ngspice 初始化失败: {type(exc).__name__}: {exc}") from exc


def _as_float(node_result: Any) -> float:
    array = np.asarray(node_result, dtype=float).reshape(-1)
    if array.size == 0:
        raise SpiceRunError("节点结果为空")
    return float(array[0])


def _branch_current(analysis: Any, name: str) -> np.ndarray:
    """读取独立源/电感支路电流，ngspice 返回的键为小写元件名。"""
    for key in (name.lower(), name):
        try:
            return np.asarray(analysis.branches[key], dtype=float).reshape(-1)
        except (KeyError, ValueError, TypeError):
            continue
    raise SpiceRunError(f"支路电流不存在: {name}")


def run_operating_point(
    circuit: Circuit,
    nodes: Sequence[str],
    temperature_c: float = 25.0,
    branches: Sequence[str] = (),
) -> dict[str, float]:
    sim = _simulator(circuit, temperature_c)
    try:
        analysis = sim.operating_point()
    except Exception as exc:  # noqa: BLE001
        raise SpiceRunError(f"ngspice 工作点求解失败: {type(exc).__name__}: {exc}") from exc
    _count_solve()
    result = {node: _as_float(analysis[node]) for node in nodes}
    for name in branches:
        result[f"I:{name.lower()}"] = _as_float(_branch_current(analysis, name))
    return result


def run_transient(
    circuit: Circuit,
    *,
    duration_s: float,
    step_s: float,
    max_step_s: float | None = None,
    nodes: Sequence[str],
    temperature_c: float = 25.0,
    reltol: float = 1e-5,
    abstol: float = 1e-10,
    vntol: float = 1e-7,
    branches: Sequence[str] = (),
) -> dict[str, np.ndarray]:
    if duration_s <= 0.0 or step_s <= 0.0:
        raise SpiceRunError("瞬态时长与步长必须为正")
    sim = _simulator(circuit, temperature_c)
    try:
        sim.options(reltol=reltol, abstol=abstol, vntol=vntol)
        analysis = sim.transient(
            step_time=step_s,
            end_time=duration_s,
            start_time=0,
            max_time=max_step_s or step_s,
        )
    except Exception as exc:  # noqa: BLE001
        raise SpiceRunError(f"ngspice 瞬态求解失败: {type(exc).__name__}: {exc}") from exc
    _count_solve()
    data: dict[str, np.ndarray] = {"time_s": np.asarray(analysis.time, dtype=float)}
    for node in nodes:
        data[node] = np.asarray(analysis[node], dtype=float)
    for name in branches:
        data[f"I:{name.lower()}"] = _branch_current(analysis, name)
    if not np.isfinite(data["time_s"]).all():
        raise SpiceRunError("瞬态结果包含非有限时间")
    return data


def run_dc_sweep(
    circuit: Circuit,
    *,
    source_name: str,
    start: float,
    stop: float,
    step: float,
    nodes: Sequence[str],
    temperature_c: float = 25.0,
) -> dict[str, np.ndarray]:
    """真实 ngspice 直流扫描。source_name 必须与网表中独立源名称一致。"""
    if step == 0.0 or (stop - start) / step < 0.0:
        raise SpiceRunError("直流扫描范围与步长非法")
    sim = _simulator(circuit, temperature_c)
    try:
        analysis = sim.dc(**{source_name: slice(float(start), float(stop) + 0.5 * abs(float(step)), float(step))})
    except Exception as exc:  # noqa: BLE001
        raise SpiceRunError(f"ngspice 直流扫描失败: {type(exc).__name__}: {exc}") from exc
    _count_solve()
    first_node = np.asarray(analysis[nodes[0]], dtype=float).reshape(-1)
    count = int(first_node.size)
    grid = float(start) + np.arange(count, dtype=float) * float(step)
    data: dict[str, np.ndarray] = {"sweep": grid}
    for node in nodes:
        data[node] = np.asarray(analysis[node], dtype=float).reshape(-1)[:count]
    return data


def run_ac_sweep(
    circuit: Circuit,
    *,
    start_hz: float,
    stop_hz: float,
    points_per_decade: int = 50,
    nodes: Sequence[str],
    temperature_c: float = 25.0,
) -> dict[str, Any]:
    if start_hz <= 0.0 or stop_hz <= start_hz:
        raise SpiceRunError("AC 扫频范围非法")
    sim = _simulator(circuit, temperature_c)
    try:
        analysis = sim.ac(
            start_frequency=start_hz,
            stop_frequency=stop_hz,
            number_of_points=points_per_decade,
            variation="dec",
        )
    except Exception as exc:  # noqa: BLE001
        raise SpiceRunError(f"ngspice AC 求解失败: {type(exc).__name__}: {exc}") from exc
    _count_solve()
    data: dict[str, Any] = {"frequency_hz": np.asarray(analysis.frequency, dtype=float)}
    for node in nodes:
        data[node] = np.asarray(analysis[node], dtype=complex)
    return data


def save_netlist(circuit: Circuit, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(circuit), encoding="utf-8")
    return path


def db20(magnitude: float) -> float:
    if magnitude <= 0.0:
        return float("-inf")
    return 20.0 * float(np.log10(magnitude))

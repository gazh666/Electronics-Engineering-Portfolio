"""仿真波形提取。

原则：
- 所有输出都是独立 NumPy 副本，不把 PySpice 内部对象暴露给上层；
- 交流数据保留复数，绝不强制 ``dtype=float`` 丢弃虚部；
- 节点 / 支路缺失、非有限值、长度不一致都抛 :class:`InvalidWaveformError`。

电流方向约定：SPICE 电压源支路电流以"从正节点流入源内部"为正，
因此向无源负载供电时该值为负。:func:`supply_current` 提供显式取反，
禁止用 ``abs`` 掩盖方向问题。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .exceptions import InvalidWaveformError

_SWEEP_PSEUDO_NODES = ("v-sweep", "i-sweep", "temp-sweep")


def extract_real_waveform(waveform: Any, name: str = "waveform") -> np.ndarray:
    """提取一维实数波形（复制并校验有限性）。"""
    values = np.array(waveform, dtype=float, copy=True)
    if values.ndim != 1:
        raise InvalidWaveformError(f"{name} must be one-dimensional, got shape {values.shape}")
    if values.size == 0:
        raise InvalidWaveformError(f"{name} is empty")
    if not np.isfinite(values).all():
        raise InvalidWaveformError(f"{name} contains NaN or Infinity")
    return values


def extract_complex_waveform(waveform: Any, name: str = "waveform") -> np.ndarray:
    """提取一维复数波形，保留实部与虚部。"""
    values = np.array(waveform, dtype=complex, copy=True)
    if values.ndim != 1:
        raise InvalidWaveformError(f"{name} must be one-dimensional, got shape {values.shape}")
    if values.size == 0:
        raise InvalidWaveformError(f"{name} is empty")
    if not np.isfinite(values.real).all() or not np.isfinite(values.imag).all():
        raise InvalidWaveformError(f"{name} contains NaN or Infinity")
    return values


def _available(keys: Any) -> str:
    return ", ".join(sorted(str(key) for key in keys)) or "<none>"


def node_waveform(analysis: Any, node: str, *, complex_data: bool = False) -> np.ndarray:
    """提取节点电压波形。"""
    nodes = getattr(analysis, "nodes", {})
    if node not in nodes:
        raise InvalidWaveformError(f"node {node!r} not found; available: {_available(nodes)}")
    if complex_data:
        return extract_complex_waveform(nodes[node], f"V({node})")
    return extract_real_waveform(nodes[node], f"V({node})")


def source_branch_key(source_name: str) -> str:
    """把用户提供的源名转换为 ngspice 支路键（如 ``input`` → ``vinput``）。"""
    if not isinstance(source_name, str) or not source_name.strip():
        raise ValueError("source_name must be a non-empty string")
    key = source_name.strip().lower()
    return key if key.startswith("v") else f"v{key}"


def branch_waveform(analysis: Any, branch_name: str, *, complex_data: bool = False) -> np.ndarray:
    """提取支路电流波形（键名由 :func:`source_branch_key` 生成）。"""
    branches = getattr(analysis, "branches", {})
    if branch_name not in branches:
        raise InvalidWaveformError(
            f"branch {branch_name!r} not found; available: {_available(branches)}"
        )
    if complex_data:
        return extract_complex_waveform(branches[branch_name], f"I({branch_name})")
    return extract_real_waveform(branches[branch_name], f"I({branch_name})")


def source_branch_waveform(
    analysis: Any, source_name: str, *, complex_data: bool = False
) -> np.ndarray:
    """按源名提取电压源支路电流（原始 SPICE 方向）。"""
    return branch_waveform(analysis, source_branch_key(source_name), complex_data=complex_data)


def supply_current(branch_current: np.ndarray) -> np.ndarray:
    """把 SPICE 源支路电流转换为"电源向电路输出"的电流。

    ``i(Vsource)`` 以流入源内部为正，因此供电电流等于其相反数。
    该函数显式取反并保留符号，禁止用 ``abs`` 抹掉方向信息。
    """
    values = np.array(branch_current, dtype=float, copy=True)
    return -values


def extract_operating_point_nodes(analysis: Any) -> dict[str, float]:
    """提取工作点节点电压（标量）。"""
    nodes = getattr(analysis, "nodes", {})
    if not nodes:
        raise InvalidWaveformError("operating point contains no nodes")
    result: dict[str, float] = {}
    for name, waveform in nodes.items():
        values = extract_real_waveform(waveform, f"V({name})")
        if values.size != 1:
            raise InvalidWaveformError(f"operating point V({name}) must have exactly one value")
        result[str(name)] = float(values[0])
    return result


def extract_operating_point_branches(analysis: Any) -> dict[str, float]:
    """提取工作点电压源支路电流（原始 SPICE 方向）。"""
    branches = getattr(analysis, "branches", {})
    result: dict[str, float] = {}
    for name, waveform in branches.items():
        values = extract_real_waveform(waveform, f"I({name})")
        if values.size != 1:
            raise InvalidWaveformError(f"operating point I({name}) must have exactly one value")
        result[str(name)] = float(values[0])
    return result


def extract_dc_sweep(analysis: Any) -> np.ndarray:
    """提取直流扫描横坐标（单位 V 或 A，取决于扫描源）。"""
    sweep = getattr(analysis, "sweep", None)
    if sweep is None:
        raise InvalidWaveformError("DC analysis has no sweep axis")
    return extract_real_waveform(sweep, "DC sweep")


def extract_transient_time(analysis: Any) -> np.ndarray:
    """提取瞬态时间轴（秒）。"""
    time = getattr(analysis, "time", None)
    if time is None:
        raise InvalidWaveformError("transient analysis has no time axis")
    return extract_real_waveform(time, "transient time")


def extract_ac_frequency(analysis: Any) -> np.ndarray:
    """提取交流频率轴（Hz）。"""
    frequency = getattr(analysis, "frequency", None)
    if frequency is None:
        raise InvalidWaveformError("AC analysis has no frequency axis")
    return extract_real_waveform(frequency, "AC frequency")


def extract_ac_node_parts(analysis: Any, node: str) -> tuple[np.ndarray, np.ndarray]:
    """提取交流节点电压的实部与虚部。"""
    values = node_waveform(analysis, node, complex_data=True)
    return values.real.copy(), values.imag.copy()


def extract_ac_branch_parts(analysis: Any, branch_name: str) -> tuple[np.ndarray, np.ndarray]:
    """提取交流支路电流的实部与虚部（``branch_name`` 为 ngspice 支路键）。"""
    values = branch_waveform(analysis, branch_name, complex_data=True)
    return values.real.copy(), values.imag.copy()


def analysis_nodes(analysis: Any, *, include_sweep: bool = False) -> list[str]:
    """返回真实电路节点名（默认排除 DC 扫描伪节点）。"""
    nodes = list(getattr(analysis, "nodes", {}).keys())
    if include_sweep:
        return nodes
    return [name for name in nodes if name not in _SWEEP_PSEUDO_NODES]


def analysis_branches(analysis: Any) -> list[str]:
    """返回电压源支路名。"""
    return list(getattr(analysis, "branches", {}).keys())


def require_equal_lengths(**arrays: np.ndarray) -> int:
    """校验多个一维数组长度一致，返回公共长度。"""
    if not arrays:
        raise ValueError("at least one array is required")
    lengths = {name: len(value) for name, value in arrays.items()}
    if len(set(lengths.values())) != 1:
        raise InvalidWaveformError(f"length mismatch: {lengths}")
    return next(iter(lengths.values()))

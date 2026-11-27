"""统一时间域计算工具。

第五阶段所有时域指标都经过本模块，保证：

- 时间平均使用梯形积分 ``∫x dt / ∫dt``，不用算术平均替代非均匀采样时间平均；
- 时间窗口边界用线性插值补齐，不超出原始数据覆盖范围；
- 非法数据（NaN / Infinity / 重复时间 / 倒序时间）显式报错；
- 峰值始终来自原始波形，不做平滑后再取峰。

第三阶段 ``analysis.steady_state`` 与第四阶段 ``analysis.power_metrics`` 已各自实现了
部分同类函数；本模块统一口径并提供更完整的接口，旧函数保持兼容、不重复改写。
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _integrate(values: np.ndarray, time: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(values, time))
    return float(np.trapz(values, time))  # pragma: no cover - NumPy < 2.0


def validate_time_series(time_s: Any, values: Any, name: str = "values") -> tuple[np.ndarray, np.ndarray]:
    """校验一维、等长、有限、严格递增的时间序列。"""
    time = np.asarray(time_s, dtype=float)
    array = np.asarray(values, dtype=float)
    if time.ndim != 1 or array.ndim != 1:
        raise ValueError("Expected one-dimensional arrays")
    if time.shape != array.shape:
        raise ValueError("Shape mismatch")
    if time.size < 2:
        raise ValueError("Insufficient data")
    if not np.isfinite(time).all():
        raise ValueError("Invalid time data")
    if not np.isfinite(array).all():
        raise ValueError(f"Invalid waveform: {name}")
    if np.any(np.diff(time) <= 0):
        raise ValueError("Time must increase")
    return time, array


def clip_time_window(
    time_s: Any,
    values: Any,
    start_s: float,
    end_s: float,
    name: str = "values",
) -> tuple[np.ndarray, np.ndarray]:
    """截取 ``[start_s, end_s]``，边界线性插值；超出范围直接报错。"""
    time, array = validate_time_series(time_s, values, name)
    start = float(start_s)
    end = float(end_s)
    if not np.isfinite(start) or not np.isfinite(end):
        raise ValueError("window bounds must be finite")
    if end <= start:
        raise ValueError("Invalid analysis window")
    tolerance = max(1e-15, abs(float(time[-1] - time[0])) * 1e-12)
    if start < float(time[0]) - tolerance:
        raise ValueError("Start outside data range")
    if end > float(time[-1]) + tolerance:
        raise ValueError("End outside data range")
    start = max(start, float(time[0]))
    end = min(end, float(time[-1]))

    mask = (time > start) & (time < end)
    inner_time = time[mask]
    inner_values = array[mask]
    window_time = np.concatenate(([start], inner_time, [end]))
    window_values = np.concatenate(
        (
            [np.interp(start, time, array)],
            inner_values,
            [np.interp(end, time, array)],
        )
    )
    if window_time.size < 2:
        raise ValueError("Insufficient data in window")
    return window_time, window_values


def time_weighted_mean(time_s: Any, values: Any) -> float:
    """时间加权平均 ``∫x dt / T``。"""
    time, array = validate_time_series(time_s, values)
    duration = float(time[-1] - time[0])
    if duration <= 0:
        raise ValueError("time window must have positive duration")
    return _integrate(array, time) / duration


def time_integral(time_s: Any, values: Any) -> float:
    """时间积分 ``∫x dt``。"""
    time, array = validate_time_series(time_s, values)
    return _integrate(array, time)


def time_weighted_rms(time_s: Any, values: Any) -> float:
    """时间加权有效值 ``sqrt(∫x²dt / T)``。"""
    time, array = validate_time_series(time_s, values)
    duration = float(time[-1] - time[0])
    if duration <= 0:
        raise ValueError("time window must have positive duration")
    mean_square = _integrate(array * array, time) / duration
    return float(np.sqrt(max(mean_square, 0.0)))


def time_weighted_ac_rms(time_s: Any, values: Any) -> float:
    """去直流后的交流有效值。"""
    time, array = validate_time_series(time_s, values)
    dc_value = time_weighted_mean(time, array)
    return time_weighted_rms(time, array - dc_value)


def time_weighted_std(time_s: Any, values: Any) -> float:
    """时间加权标准差（围绕时间加权均值）。"""
    time, array = validate_time_series(time_s, values)
    mean = time_weighted_mean(time, array)
    return time_weighted_rms(time, array - mean)


def peak_to_peak(values: Any) -> float:
    """峰峰值 ``max - min``；始终来自原始样本。"""
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        raise ValueError("Empty waveform")
    if not np.isfinite(array).all():
        raise ValueError("Invalid waveform")
    return float(np.max(array) - np.min(array))


def minimum_value(values: Any) -> float:
    array = np.asarray(values, dtype=float)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("Invalid waveform")
    return float(np.min(array))


def maximum_value(values: Any) -> float:
    array = np.asarray(values, dtype=float)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("Invalid waveform")
    return float(np.max(array))


def time_step_statistics(time_s: Any) -> dict[str, float | int | bool]:
    """原始采样间隔统计，供频谱可信频段与开关边沿分辨率判断使用。"""
    time = np.asarray(time_s, dtype=float)
    if time.ndim != 1 or time.size < 2:
        raise ValueError("Insufficient data")
    if not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        raise ValueError("Time must be finite and strictly increasing")
    steps = np.diff(time)
    return {
        "sample_count": int(time.size),
        "duration_s": float(time[-1] - time[0]),
        "min_step_s": float(np.min(steps)),
        "max_step_s": float(np.max(steps)),
        "mean_step_s": float(np.mean(steps)),
        "median_step_s": float(np.median(steps)),
    }

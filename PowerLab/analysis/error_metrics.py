"""理论与仿真误差分析。

采样点统计误差之外，针对非均匀瞬态采样提供时间加权误差；
不同时间轴通过插值对齐；理论参考值为 0 时相对误差明确标记为不可定义。
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np


def _pair(simulated: Any, theoretical: Any) -> tuple[np.ndarray, np.ndarray]:
    sim = np.asarray(simulated, dtype=float)
    theory = np.asarray(theoretical, dtype=float)
    if sim.shape != theory.shape:
        raise ValueError(f"shape mismatch: simulated {sim.shape} vs theoretical {theory.shape}")
    if sim.size == 0:
        raise ValueError("input arrays must not be empty")
    if not np.isfinite(sim).all():
        raise ValueError("simulated data contains NaN or Infinity")
    if not np.isfinite(theory).all():
        raise ValueError("theoretical data contains NaN or Infinity")
    return sim, theory


def absolute_error(simulated: Any, theoretical: Any) -> np.ndarray:
    """绝对误差 simulated − theoretical。"""
    sim, theory = _pair(simulated, theoretical)
    return sim - theory


def relative_error(simulated: Any, theoretical: Any) -> np.ndarray:
    """相对误差 (sim − theory) / theory。

    理论值为 0 的点返回 ``NaN``，并可通过 :func:`zero_reference_count` 统计。
    这样既不会伪造 0 误差，也不会让整个数组不可用。
    """
    sim, theory = _pair(simulated, theoretical)
    result = np.full(sim.shape, np.nan, dtype=float)
    nonzero = theory != 0
    result[nonzero] = (sim[nonzero] - theory[nonzero]) / theory[nonzero]
    return result


def relative_error_percent(simulated: Any, theoretical: Any) -> np.ndarray:
    """相对误差百分数；理论值为 0 的位置为 ``NaN``。"""
    return relative_error(simulated, theoretical) * 100.0


def zero_reference_count(theoretical: Any) -> int:
    """统计理论参考值恰好为 0 的采样点数量。"""
    theory = np.asarray(theoretical, dtype=float)
    return int(np.count_nonzero(theory == 0))


def scalar_relative_error_percent(measured: float, reference: float) -> float | None:
    """标量相对误差百分数；``reference == 0`` 时返回 ``None``（不可定义）。"""
    measured = float(measured)
    reference = float(reference)
    if reference == 0:
        return None
    return (measured - reference) / reference * 100.0


def calculate_error_metrics(simulated: Any, theoretical: Any) -> dict[str, Any]:
    """采样点统计误差：MAE、RMSE、最大绝对误差及其位置。"""
    sim, theory = _pair(simulated, theoretical)
    error = sim - theory
    absolute = np.abs(error)
    index = int(np.argmax(absolute))
    return {
        "sample_count": int(sim.size),
        "mae": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "max_absolute_error": float(absolute[index]),
        "max_absolute_error_index": index,
        "zero_reference_count": zero_reference_count(theory),
        "data_source": "comparison",
    }


def _validate_time(time_s: Any, *arrays: np.ndarray) -> np.ndarray:
    time = np.asarray(time_s, dtype=float)
    if time.ndim != 1 or time.size < 2:
        raise ValueError("time_s must be a 1D array with at least two samples")
    if not np.isfinite(time).all():
        raise ValueError("time_s contains NaN or Infinity")
    if not np.all(np.diff(time) > 0):
        raise ValueError("time_s must be strictly increasing")
    for array in arrays:
        if array.size != time.size:
            raise ValueError("time and data must have the same length")
    return time


def time_weighted_error_metrics(
    time_s: Any,
    simulated: Any,
    theoretical: Any,
) -> dict[str, Any]:
    """时间加权误差（梯形积分），适用于非均匀瞬态采样。

    ``MAE_time = ∫|e|dt / ∫dt``，``RMSE_time = sqrt(∫e²dt / ∫dt)``。
    """
    sim, theory = _pair(simulated, theoretical)
    time = _validate_time(time_s, sim, theory)
    error = sim - theory
    span = float(time[-1] - time[0])
    if span <= 0:
        raise ValueError("time span must be positive")

    if hasattr(np, "trapezoid"):
        integrate = np.trapezoid
    else:  # numpy < 2
        integrate = np.trapz

    mae_time = float(integrate(np.abs(error), time) / span)
    rmse_time = float(np.sqrt(integrate(error**2, time) / span))
    max_abs = float(np.max(np.abs(error)))

    dt = np.diff(time)
    weights = np.zeros_like(time)
    weights[:-1] += dt / 2.0
    weights[1:] += dt / 2.0
    mae_weighted = float(np.sum(np.abs(error) * weights) / span)
    rmse_weighted = float(np.sqrt(np.sum(error**2 * weights) / span))

    return {
        "time_span_s": span,
        "mae_time_weighted": mae_time,
        "rmse_time_weighted": rmse_time,
        "mae_weight_sum": mae_weighted,
        "rmse_weight_sum": rmse_weighted,
        "max_absolute_error": max_abs,
        "sample_count": int(sim.size),
        "nonuniform_sampling": bool(np.max(dt) > np.min(dt) * 1.05),
        "data_source": "comparison",
    }


def interpolate_to_time_axis(
    source_time_s: Any,
    source_values: Any,
    target_time_s: Any,
) -> np.ndarray:
    """把 ``source`` 波形线性插值到 ``target`` 时间轴。

    ``target`` 必须完全落在 ``source`` 的时间范围内，不做外推。
    """
    source_time = np.asarray(source_time_s, dtype=float)
    source_values = np.asarray(source_values, dtype=float)
    target_time = np.asarray(target_time_s, dtype=float)

    if source_time.ndim != 1 or source_values.ndim != 1:
        raise ValueError("source time and values must be one-dimensional")
    if source_time.size != source_values.size or source_time.size < 2:
        raise ValueError("source time and values must have equal length >= 2")
    if not np.isfinite(source_time).all() or not np.isfinite(source_values).all():
        raise ValueError("source data contains NaN or Infinity")
    if not np.all(np.diff(source_time) > 0):
        raise ValueError("source time must be strictly increasing")
    if target_time.size and (
        target_time.min() < source_time[0] or target_time.max() > source_time[-1]
    ):
        raise ValueError("target time axis exceeds source range; extrapolation is not allowed")
    return np.interp(target_time, source_time, source_values)


def aligned_error_metrics(
    simulation_time_s: Any,
    simulated: Any,
    theory_time_s: Any,
    theoretical: Any,
    *,
    time_weighted: bool = True,
) -> dict[str, Any]:
    """把理论数据插值到仿真时间轴后计算误差。

    不同时间轴不允许直接逐点比较，必须先对齐。
    """
    sim_time = np.asarray(simulation_time_s, dtype=float)
    theory_on_sim = interpolate_to_time_axis(theory_time_s, theoretical, sim_time)
    metrics = calculate_error_metrics(simulated, theory_on_sim)
    metrics["interpolation"] = "linear, theory -> simulation time axis"
    if time_weighted:
        metrics["time_weighted"] = time_weighted_error_metrics(sim_time, simulated, theory_on_sim)
    return metrics


def cutoff_frequency_error(simulated_hz: float, theoretical_hz: float) -> dict[str, Any]:
    """截止频率误差（Hz 与相对百分数）。"""
    simulated_hz = float(simulated_hz)
    theoretical_hz = float(theoretical_hz)
    if not np.isfinite(simulated_hz) or not np.isfinite(theoretical_hz):
        raise ValueError("cutoff frequencies must be finite")
    if theoretical_hz <= 0:
        raise ValueError("theoretical cutoff frequency must be positive")
    absolute = simulated_hz - theoretical_hz
    return {
        "simulated_hz": simulated_hz,
        "theoretical_hz": theoretical_hz,
        "absolute_error_hz": absolute,
        "relative_error_percent": absolute / theoretical_hz * 100.0,
    }


def error_near_time_constant(
    time_s: Any,
    simulated: Any,
    theoretical: Any,
    tau_s: float,
    *,
    relative_window: float = 0.05,
) -> dict[str, Any]:
    """时间常数附近（默认 tau ±5%）的误差统计。"""
    tau = float(tau_s)
    if not np.isfinite(tau) or tau <= 0:
        raise ValueError("tau_s must be a finite positive number")
    if not 0 < relative_window < 1:
        raise ValueError("relative_window must be in (0, 1)")

    time = np.asarray(time_s, dtype=float)
    sim = np.asarray(simulated, dtype=float)
    theory = np.asarray(theoretical, dtype=float)
    if time.shape != sim.shape or sim.shape != theory.shape:
        raise ValueError("time, simulated and theoretical arrays must have the same shape")
    _validate_time(time, sim, theory)

    low = tau * (1.0 - relative_window)
    high = tau * (1.0 + relative_window)
    mask = (time >= low) & (time <= high)
    if not np.any(mask):
        raise ValueError("no samples inside the requested time-constant window")

    window_metrics = calculate_error_metrics(sim[mask], theory[mask])
    window_metrics.update(
        {
            "tau_s": tau,
            "window_s": [low, high],
            "relative_window": relative_window,
            "samples_in_window": int(np.count_nonzero(mask)),
        }
    )
    return window_metrics


def format_metrics(metrics: Mapping[str, Any]) -> str:
    """把误差指标格式化为单行文本（用于命令行输出）。"""
    parts = [f"{key}={value}" for key, value in metrics.items() if isinstance(value, (int, float))]
    return ", ".join(parts)

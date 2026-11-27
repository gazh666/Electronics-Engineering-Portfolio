"""开关级充电波形指标：PWM 周期平均、纹波与 CC/CV 调节精度。

开关级仿真得到的瞬时电流/电压含有开关纹波，直接与直流量比较会系统性放大误差。
因此验收指标统一基于"每周期平均"序列；瞬时峰值与纹波另行报告，不混用。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from analysis.charging_energy import _as_series, _as_time, integrate_trapezoid


def switching_period_average(
    time_s: Any,
    values: Any,
    frequency_hz: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """按 PWM 周期分组做时间加权平均。

    返回 ``(time_center_s, period_average, period_peak_to_peak, sample_count)``。
    周期内少于 2 个采样点的分组会被丢弃（无法定义平均）。
    """
    t = _as_time(time_s)
    y = _as_series("values", values, t.size)
    if not math.isfinite(frequency_hz) or frequency_hz <= 0.0:
        raise ValueError("开关频率必须为正")

    index = np.floor(t * frequency_hz).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, index[1:] != index[:-1]])
    ends = np.r_[starts[1:], index.size]

    center: list[float] = []
    average: list[float] = []
    peak_to_peak: list[float] = []
    counts: list[int] = []
    for start, stop in zip(starts, ends):
        if stop - start < 2:
            continue
        segment_t = t[start:stop]
        segment_y = y[start:stop]
        duration = float(segment_t[-1] - segment_t[0])
        if duration <= 0.0:
            continue
        center.append(0.5 * float(segment_t[0] + segment_t[-1]))
        average.append(integrate_trapezoid(segment_y, segment_t) / duration)
        peak_to_peak.append(float(segment_y.max() - segment_y.min()))
        counts.append(int(stop - start))

    if len(center) < 2:
        raise ValueError("可用 PWM 周期不足，检查仿真步长或时长")

    return (
        np.asarray(center, dtype=float),
        np.asarray(average, dtype=float),
        np.asarray(peak_to_peak, dtype=float),
        np.asarray(counts, dtype=int),
    )


def _windowed_period_data(
    time_s: Any,
    values: Any,
    frequency_hz: float,
    window_s: float | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = _as_time(time_s)
    y = _as_series("values", values, t.size)
    start = t[0] if window_s is None else float(t[-1] - window_s)
    if window_s is not None and window_s <= 0.0:
        raise ValueError("统计窗口必须为正")
    mask = t >= start
    if mask.sum() < 3:
        raise ValueError("统计窗口内采样点不足")
    center, average, ripple, _ = switching_period_average(t[mask], y[mask], frequency_hz)
    return center, average, ripple


def _regulation_metrics(
    time_s: Any,
    values: Any,
    target: float,
    frequency_hz: float,
    window_s: float | None,
    unit: str,
) -> dict[str, Any]:
    if not math.isfinite(target):
        raise ValueError("目标值必须有限")
    _, average, ripple = _windowed_period_data(time_s, values, frequency_hz, window_s)
    error = average - target
    return {
        f"mean_period_average_{unit}": float(average.mean()),
        f"mean_error_{unit}": float(error.mean()),
        f"mae_{unit}": float(np.abs(error).mean()),
        f"peak_error_{unit}": float(np.abs(error).max()),
        f"ripple_pp_{unit}": float(ripple.mean()),
        "periods": int(average.size),
        "window_s": None if window_s is None else float(window_s),
    }


def cc_regulation_metrics(
    time_s: Any,
    charging_current_a: Any,
    reference_a: float,
    frequency_hz: float,
    window_s: float | None = None,
) -> dict[str, Any]:
    metrics = _regulation_metrics(time_s, charging_current_a, reference_a, frequency_hz, window_s, "a")
    t = _as_time(time_s)
    y = _as_series("charging_current_a", charging_current_a, t.size)
    _, average, _ = _windowed_period_data(t, y, frequency_hz, None)
    peak = float(average.max())
    metrics["peak_period_average_a"] = peak
    metrics["overshoot_fraction"] = max(0.0, (peak - reference_a) / reference_a)
    return metrics


def cv_regulation_metrics(
    time_s: Any,
    pack_voltage_v: Any,
    target_v: float,
    frequency_hz: float,
    window_s: float | None = None,
) -> dict[str, Any]:
    metrics = _regulation_metrics(time_s, pack_voltage_v, target_v, frequency_hz, window_s, "v")
    t = _as_time(time_s)
    y = _as_series("pack_voltage_v", pack_voltage_v, t.size)
    _, average, _ = _windowed_period_data(t, y, frequency_hz, None)
    peak = float(average.max())
    metrics["peak_period_average_v"] = peak
    metrics["overshoot_v"] = max(0.0, peak - target_v)
    return metrics


def settling_time_s(
    time_s: Any,
    values: Any,
    target: float,
    tolerance: float,
    frequency_hz: float | None = None,
    start_s: float = 0.0,
) -> float | None:
    """首次进入且此后再不离开 ``target ± tolerance`` 的时间（相对 ``start_s``）。

    给定 ``frequency_hz`` 时先在周期平均序列上判定，避免开关纹波触发假进入。
    """
    t = _as_time(time_s)
    if frequency_hz is not None:
        center, average, _, _ = switching_period_average(t, values, frequency_hz)
        t, y = center, average
    else:
        y = _as_series("values", values, t.size)
    if not math.isfinite(target) or not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("目标或容差非法")

    inside = np.abs(y - target) <= tolerance
    outside_indices = np.flatnonzero(~inside)
    if outside_indices.size == 0:
        index = 0
    else:
        last_outside = int(outside_indices[-1])
        if last_outside == y.size - 1:
            return None
        index = last_outside + 1
    candidate = float(t[index])
    if candidate < start_s:
        return 0.0
    return candidate - float(t[0])

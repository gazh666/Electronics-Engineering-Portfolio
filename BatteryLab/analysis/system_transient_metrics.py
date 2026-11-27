"""瞬态指标：稳态建立时间、跌落与超调。"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def find_settling_time(
    time_s: Sequence[float],
    values: Sequence[float],
    reference: float,
    tolerance: float,
    *,
    hold_time_s: float = 5e-4,
) -> float | None:
    """稳态建立时间 = 最后一次超出误差带之后重新进入并保持的时刻。

    返回 ``None`` 表示全程未进入误差带，或剩余保持时长不足 ``hold_time_s``。
    """
    t = np.asarray(time_s, dtype=float)
    v = np.asarray(values, dtype=float)
    if t.shape != v.shape or t.ndim != 1:
        raise ValueError("时间与数值长度不一致")
    if tolerance <= 0:
        raise ValueError("误差带必须为正")
    if len(t) < 2:
        raise ValueError("样本不足")
    if not (np.isfinite(t).all() and np.isfinite(v).all()):
        raise ValueError("窗口包含非有限值")
    if np.any(np.diff(t) < 0):
        raise ValueError("时间必须单调不减")
    outside = np.abs(v - reference) > tolerance
    last_outside = np.flatnonzero(outside)
    if outside.all():
        return None
    start_index = 0 if last_outside.size == 0 else int(last_outside[-1]) + 1
    if start_index >= len(t):
        return None
    if t[-1] - t[start_index] < hold_time_s:
        return None
    return float(t[start_index])


def step_metrics(
    time_s: Sequence[float],
    values: Sequence[float],
    *,
    step_time_s: float,
    pre_window_s: float = 2e-4,
    post_window_s: float = 2e-3,
    nominal_v: float | None = None,
) -> dict[str, float | None]:
    t = np.asarray(time_s, dtype=float)
    v = np.asarray(values, dtype=float)
    pre_mask = (t >= step_time_s - pre_window_s) & (t < step_time_s)
    post_mask = (t >= step_time_s) & (t <= step_time_s + post_window_s)
    if pre_mask.sum() < 5 or post_mask.sum() < 5:
        return {"status": "INSUFFICIENT_SAMPLES"}
    pre_mean = float(np.mean(v[pre_mask]))
    post = v[post_mask]
    post_time = t[post_mask]
    minimum = float(np.min(post))
    maximum = float(np.max(post))
    reference = float(nominal_v if nominal_v is not None else np.mean(v[t >= step_time_s + post_window_s * 0.8]))
    return {
        "status": "OK",
        "pre_step_mean_v": pre_mean,
        "post_step_min_v": minimum,
        "post_step_max_v": maximum,
        "droop_v": max(pre_mean - minimum, 0.0),
        "overshoot_v": max(maximum - pre_mean, 0.0),
        "deviation_v": max(abs(maximum - pre_mean), abs(pre_mean - minimum)),
        "min_time_s": float(post_time[int(np.argmin(post))]),
        "max_time_s": float(post_time[int(np.argmax(post))]),
        "reference_v": reference,
    }


def ripple(values: Sequence[float], *, mask: Sequence[bool] | None = None) -> float | None:
    v = np.asarray(values, dtype=float)
    if mask is not None:
        v = v[np.asarray(mask, dtype=bool)]
    if v.size < 10:
        return None
    return float(np.max(v) - np.min(v))


__all__ = ["find_settling_time", "ripple", "step_metrics"]

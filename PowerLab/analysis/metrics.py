"""工程指标分析：误差、检查点电压、最大误差与 RMSE。

所有函数只做数值计算与校验，不接触仿真引擎。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np


def relative_error_percent(measured: float, reference: float) -> float:
    """相对误差 (measured − reference) / reference × 100。"""
    if reference == 0:
        raise ValueError("reference 不能为 0")
    return (measured - reference) / reference * 100.0


def divider_metrics(vin: float, vout: float, theoretical_vout: float, theoretical_current: float) -> dict[str, Any]:
    return {
        "vin_v": vin,
        "vout_v": vout,
        "theoretical_vout_v": theoretical_vout,
        "absolute_error_v": abs(vout - theoretical_vout),
        "relative_error_percent": relative_error_percent(vout, theoretical_vout),
        "theoretical_current_a": theoretical_current,
    }


def validate_time_series(time_s: Sequence[float], values: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    """校验时间序列：一维、非空、有限、严格递增。"""
    time_array = np.asarray(time_s, dtype=float)
    value_array = np.asarray(values, dtype=float)
    if time_array.ndim != 1 or value_array.ndim != 1:
        raise ValueError("时间与电压必须是一维数组")
    if time_array.size < 2 or time_array.size != value_array.size:
        raise ValueError("时间与电压长度必须一致且至少包含 2 个点")
    if not np.isfinite(time_array).all() or not np.isfinite(value_array).all():
        raise ValueError("时间或电压包含 NaN / Infinity")
    if not np.all(np.diff(time_array) > 0):
        raise ValueError("时间序列必须严格递增")
    return time_array, value_array


def rc_metrics(
    time_s: Sequence[float],
    vout_v: Sequence[float],
    *,
    vin_v: float,
    tau_s: float,
    checkpoints_tau: Sequence[int] = (1, 2, 3, 5),
) -> dict[str, Any]:
    """计算 RC 瞬态的检查点、最大绝对误差与 RMSE。"""
    if tau_s <= 0 or not math.isfinite(tau_s):
        raise ValueError(f"tau_s 必须是有限正数，实际为 {tau_s!r}")

    time_array, value_array = validate_time_series(time_s, vout_v)
    theoretical = vin_v * (1.0 - np.exp(-time_array / tau_s))
    absolute_error = np.abs(value_array - theoretical)

    checkpoints: list[dict[str, float]] = []
    for multiple in checkpoints_tau:
        target_time = multiple * tau_s
        simulated = float(np.interp(target_time, time_array, value_array))
        ideal = float(vin_v * (1.0 - math.exp(-target_time / tau_s)))
        checkpoints.append(
            {
                "tau_multiple": float(multiple),
                "time_s": target_time,
                "simulated_v": simulated,
                "ideal_step_theoretical_v": ideal,
                "absolute_error_v": abs(simulated - ideal),
            }
        )

    return {
        "sample_count": int(time_array.size),
        "time_start_s": float(time_array[0]),
        "time_end_s": float(time_array[-1]),
        "final_simulated_v": float(value_array[-1]),
        "final_ideal_step_v": float(theoretical[-1]),
        "max_absolute_error_v": float(absolute_error.max()),
        "rmse_v": float(np.sqrt(np.mean(absolute_error**2))),
        "checkpoints": checkpoints,
    }

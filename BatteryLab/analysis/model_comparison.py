"""多模型误差计算：MAE、RMSE、最大绝对误差、带符号平均误差与时间加权误差。

所有误差结果必须注明参考对象；本模块不推断真实电芯预测精度。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


class ComparisonError(ValueError):
    """对照输入非法。"""


def _series(values: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ComparisonError(f"{name} 必须是一维数组")
    if not np.isfinite(array).all():
        raise ComparisonError(f"{name} 含有非有限数值")
    return array


def error_metrics(reference: Sequence[float], model: Sequence[float], *, reference_name: str = "reference") -> dict[str, Any]:
    reference_array = _series(reference, "reference")
    model_array = _series(model, "model")
    if reference_array.size != model_array.size:
        raise ComparisonError("参考序列与模型序列长度不一致")
    if reference_array.size == 0:
        raise ComparisonError("序列为空")
    error = model_array - reference_array
    return {
        "reference": reference_name,
        "points": int(error.size),
        "mae_v": float(np.mean(np.abs(error))),
        "rmse_v": float(np.sqrt(np.mean(error**2))),
        "max_abs_error_v": float(np.max(np.abs(error))),
        "mean_signed_error_v": float(np.mean(error)),
        "bias_v": float(np.mean(error)),
        "max_error_time_index": int(np.argmax(np.abs(error))),
    }


def time_weighted_metrics(
    time_s: Sequence[float],
    reference: Sequence[float],
    model: Sequence[float],
    *,
    reference_name: str = "reference",
) -> dict[str, Any]:
    times = _series(time_s, "time")
    reference_array = _series(reference, "reference")
    model_array = _series(model, "model")
    if not (times.size == reference_array.size == model_array.size):
        raise ComparisonError("时间、参考与模型序列长度必须一致")
    if times.size < 2:
        raise ComparisonError("至少需要两个时间点")
    if not np.all(np.diff(times) > 0):
        raise ComparisonError("时间必须严格递增")
    weights = np.diff(times)
    error = model_array - reference_array
    weighted_abs = float(np.sum(weights * np.abs(error[:-1])))
    weighted_square = float(np.sum(weights * error[:-1] ** 2))
    total = float(np.sum(weights))
    return {
        "reference": reference_name,
        "points": int(error.size),
        "weighted_mae_v": weighted_abs / total if total > 0 else None,
        "weighted_rmse_v": float(np.sqrt(weighted_square / total)) if total > 0 else None,
        "time_span_s": float(times[-1] - times[0]),
    }


def align_series(
    reference_time_s: Sequence[float],
    reference_values: Sequence[float],
    model_time_s: Sequence[float],
    model_values: Sequence[float],
    *,
    start_s: float | None = None,
    end_s: float | None = None,
    exclude_times_s: Sequence[float] = (),
    exclude_window_s: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """在共同有效时间区间建立对照轴；不超出模型数据范围外推。"""
    reference_time = _series(reference_time_s, "reference_time")
    reference = _series(reference_values, "reference_values")
    model_time = _series(model_time_s, "model_time")
    model = _series(model_values, "model_values")
    if reference_time.size != reference.size or model_time.size != model.size:
        raise ComparisonError("时间与数值长度不一致")
    if not np.all(np.diff(reference_time) > 0) or not np.all(np.diff(model_time) > 0):
        raise ComparisonError("时间必须严格递增")

    lower = max(float(reference_time[0]), float(model_time[0]), float(start_s) if start_s is not None else -np.inf)
    upper = min(float(reference_time[-1]), float(model_time[-1]), float(end_s) if end_s is not None else np.inf)
    if lower >= upper:
        raise ComparisonError("参考与模型没有重叠时间区间")
    mask = (reference_time >= lower) & (reference_time <= upper)
    for excluded in exclude_times_s:
        if exclude_window_s > 0:
            mask &= np.abs(reference_time - float(excluded)) > exclude_window_s
        else:
            mask &= np.abs(reference_time - float(excluded)) > 1e-12
    target_time = reference_time[mask]
    if target_time.size < 2:
        raise ComparisonError("对齐后有效采样点不足")
    target_reference = reference[mask]
    target_model = np.interp(target_time, model_time, model)
    return target_time, target_reference, target_model


def compare_frames(
    reference_frame: Any,
    model_frame: Any,
    *,
    reference_column: str = "terminal_voltage_v",
    model_column: str = "terminal_voltage_v",
    start_s: float | None = None,
    end_s: float | None = None,
    exclude_times_s: Sequence[float] = (),
    exclude_window_s: float = 0.0,
    reference_name: str = "reference",
) -> dict[str, Any]:
    time_s, reference, model = align_series(
        reference_frame["time_s"].to_numpy(dtype=float),
        reference_frame[reference_column].to_numpy(dtype=float),
        model_frame["time_s"].to_numpy(dtype=float),
        model_frame[model_column].to_numpy(dtype=float),
        start_s=start_s,
        end_s=end_s,
        exclude_times_s=exclude_times_s,
        exclude_window_s=exclude_window_s,
    )
    metrics = error_metrics(reference, model, reference_name=reference_name)
    metrics.update(time_weighted_metrics(time_s, reference, model, reference_name=reference_name))
    metrics["aligned_points"] = int(time_s.size)
    metrics["window_start_s"] = float(time_s[0])
    metrics["window_end_s"] = float(time_s[-1])
    return metrics

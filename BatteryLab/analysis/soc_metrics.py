"""SOC / 端电压估计工程误差评价（Task 16）。

统一约定：

- SOC 误差一律用**百分点 pp**：``(estimated - reference) × 100``；
- 参考 SOC 只允许在 ``[0, 1]`` 内参与评价（CALCE 参考轨迹因容量口径差异可能
  略低于 0，必须显式掩码并报告覆盖率）；
- ``estimated`` 为 ``None`` 的样本不参与统计，但计入总样本数以计算覆盖率；
- 时间加权指标使用零阶保持权重 ``w_i = t_{i+1} - t_i``，避免高采样率区段
  主导结果。

端电压误差必须单独计算：观测器用**修正前**的预测电压评价一步预测能力，
修正后重算的电压只能称为"后验重构电压"，两类误差不得混用。
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


class SOCMetricsError(ValueError):
    """SOC 指标输入非法。"""


def _as_array(values: Sequence[float | None]) -> np.ndarray:
    return np.asarray([np.nan if value is None else float(value) for value in values], dtype=float)


def _zoh_weights(time_s: np.ndarray) -> np.ndarray:
    if time_s.size < 2:
        return np.ones_like(time_s)
    dt = np.diff(time_s)
    weights = np.empty_like(time_s)
    weights[:-1] = dt
    weights[-1] = dt[-1]
    return weights


def calculate_soc_metrics(
    reference_soc: Sequence[float | None],
    estimated_soc: Sequence[float | None],
    time_s: Sequence[float] | None = None,
) -> dict[str, float | int | None]:
    """SOC 误差指标。返回值为百分点 pp。"""
    reference = _as_array(reference_soc)
    estimated = _as_array(estimated_soc)
    if reference.ndim != 1 or estimated.ndim != 1:
        raise SOCMetricsError("Expected 1D arrays")
    if reference.shape != estimated.shape:
        raise SOCMetricsError("Shape mismatch")
    if reference.size == 0:
        raise SOCMetricsError("Empty input")

    reference_valid = np.isfinite(reference) & (reference >= 0.0) & (reference <= 1.0)
    estimated_valid = np.isfinite(estimated)
    mask = reference_valid & estimated_valid

    total = int(reference.size)
    valid = int(np.sum(mask))
    if valid == 0:
        return {
            "mae_pp": None,
            "rmse_pp": None,
            "max_absolute_error_pp": None,
            "mean_error_pp": None,
            "final_error_pp": None,
            "p95_absolute_error_pp": None,
            "sample_count": total,
            "valid_sample_count": 0,
            "coverage_fraction": 0.0,
            "duration_s": None,
            "valid_duration_s": None,
            "time_weighted_mae_pp": None,
            "time_weighted_rmse_pp": None,
            "status": "NO_VALID_SAMPLE",
        }

    error_pp = (estimated[mask] - reference[mask]) * 100.0
    absolute = np.abs(error_pp)

    duration = None
    valid_duration = None
    weighted_mae = None
    weighted_rmse = None
    if time_s is not None:
        time_array = np.asarray([float(value) for value in time_s], dtype=float)
        if time_array.shape != reference.shape:
            raise SOCMetricsError("time_s 长度必须与 SOC 序列一致")
        if not np.isfinite(time_array).all() or np.any(np.diff(time_array) <= 0.0):
            raise SOCMetricsError("时间轴必须严格递增")
        duration = float(time_array[-1] - time_array[0])
        valid_duration = float(time_array[mask][-1] - time_array[mask][0]) if valid > 1 else 0.0
        weights = _zoh_weights(time_array)[mask]
        weight_sum = float(np.sum(weights))
        if weight_sum > 0.0:
            weighted_mae = float(np.sum(absolute * weights) / weight_sum)
            weighted_rmse = float(np.sqrt(np.sum(error_pp**2 * weights) / weight_sum))

    return {
        "mae_pp": float(np.mean(absolute)),
        "rmse_pp": float(np.sqrt(np.mean(error_pp**2))),
        "max_absolute_error_pp": float(np.max(absolute)),
        "mean_error_pp": float(np.mean(error_pp)),
        "final_error_pp": float(error_pp[-1]),
        "p95_absolute_error_pp": float(np.percentile(absolute, 95)),
        "sample_count": total,
        "valid_sample_count": valid,
        "coverage_fraction": float(valid / total),
        "duration_s": duration,
        "valid_duration_s": valid_duration,
        "time_weighted_mae_pp": weighted_mae,
        "time_weighted_rmse_pp": weighted_rmse,
        "status": "OK",
    }


def calculate_voltage_metrics(
    reference_voltage_v: Sequence[float | None],
    predicted_voltage_v: Sequence[float | None],
) -> dict[str, float | int | None]:
    """端电压预测误差（V）。仅用于修正前的一步预测电压。"""
    reference = _as_array(reference_voltage_v)
    predicted = _as_array(predicted_voltage_v)
    if reference.shape != predicted.shape or reference.size == 0:
        raise SOCMetricsError("电压序列形状非法")
    mask = np.isfinite(reference) & np.isfinite(predicted)
    if not np.any(mask):
        return {
            "mae_v": None,
            "rmse_v": None,
            "max_absolute_error_v": None,
            "valid_sample_count": 0,
            "coverage_fraction": 0.0,
        }
    error = predicted[mask] - reference[mask]
    return {
        "mae_v": float(np.mean(np.abs(error))),
        "rmse_v": float(np.sqrt(np.mean(error**2))),
        "max_absolute_error_v": float(np.max(np.abs(error))),
        "mean_error_v": float(np.mean(error)),
        "valid_sample_count": int(np.sum(mask)),
        "coverage_fraction": float(np.sum(mask) / reference.size),
    }


def soc_error_distribution(
    reference_soc: Sequence[float | None],
    estimated_soc: Sequence[float | None],
    bins: Sequence[float] = (-20, -10, -5, -2, 0, 2, 5, 10, 20),
) -> dict[str, object]:
    """SOC 误差直方图（pp），用于文档中的误差分布图。"""
    reference = _as_array(reference_soc)
    estimated = _as_array(estimated_soc)
    mask = np.isfinite(reference) & np.isfinite(estimated) & (reference >= 0.0) & (reference <= 1.0)
    error_pp = (estimated[mask] - reference[mask]) * 100.0
    if error_pp.size == 0:
        return {"bins_pp": list(bins), "counts": [], "mean_pp": None}
    edges = np.asarray(bins, dtype=float)
    counts, _ = np.histogram(error_pp, bins=edges)
    return {
        "bins_pp": [float(value) for value in edges],
        "counts": [int(value) for value in counts],
        "mean_pp": float(np.mean(error_pp)),
        "sample_count": int(error_pp.size),
    }


def soc_error_correlation_with_current(
    current_a: Sequence[float],
    reference_soc: Sequence[float | None],
    estimated_soc: Sequence[float | None],
) -> float | None:
    """SOC 误差与电流幅值的相关系数，用于识别"大电流区误差更大"。"""
    current = _as_array(current_a)
    reference = _as_array(reference_soc)
    estimated = _as_array(estimated_soc)
    mask = np.isfinite(current) & np.isfinite(reference) & np.isfinite(estimated)
    if np.sum(mask) < 3:
        return None
    error = np.abs(estimated[mask] - reference[mask])
    if np.std(error) == 0.0 or np.std(np.abs(current[mask])) == 0.0:
        return None
    return float(np.corrcoef(np.abs(current[mask]), error)[0, 1])


def non_finite_guard(value: float) -> float | None:
    """把 NaN/Inf 转成 None，便于写 JSON。"""
    return None if not math.isfinite(float(value)) else float(value)

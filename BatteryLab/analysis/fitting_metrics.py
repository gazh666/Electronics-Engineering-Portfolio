"""模型误差评价指标（内部统一 V，报告输出 mV）。

error = predicted_voltage - measured_voltage。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd


class MetricsError(ValueError):
    """误差计算输入非法。"""


def _array(values: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise MetricsError(f"{name} 必须是一维数组")
    if array.size == 0:
        raise MetricsError(f"{name} 为空")
    if not np.isfinite(array).all():
        raise MetricsError(f"{name} 包含非有限数值")
    return array


def calculate_voltage_errors(measured_voltage: Sequence[float], predicted_voltage: Sequence[float]) -> dict[str, Any]:
    measured = _array(measured_voltage, "measured_voltage")
    predicted = _array(predicted_voltage, "predicted_voltage")
    if measured.shape != predicted.shape:
        raise MetricsError("measured 与 predicted 形状不一致")
    error = predicted - measured
    return {
        "points": int(error.size),
        "mae_v": float(np.mean(np.abs(error))),
        "rmse_v": float(np.sqrt(np.mean(error**2))),
        "max_absolute_error_v": float(np.max(np.abs(error))),
        "mean_error_v": float(np.mean(error)),
        "p95_absolute_error_v": float(np.percentile(np.abs(error), 95)),
        "standard_deviation_v": float(np.std(error, ddof=1)) if error.size > 1 else 0.0,
    }


def to_millivolts(metrics: dict[str, Any]) -> dict[str, Any]:
    """把以 _v 结尾的字段转换为 _mv 字段，保留原始 V 字段。"""
    payload = dict(metrics)
    for key, value in list(metrics.items()):
        if key.endswith("_v") and isinstance(value, (int, float)) and not isinstance(value, bool):
            payload[key.replace("_v", "_mv")] = float(value) * 1000.0
    return payload


def coverage_statistics(frame: pd.DataFrame) -> dict[str, Any]:
    if "time_s" not in frame.columns:
        raise MetricsError("缺少时间列")
    payload: dict[str, Any] = {
        "raw_points": int(len(frame)),
        "time_start_s": float(frame["time_s"].min()),
        "time_end_s": float(frame["time_s"].max()),
        "time_span_s": float(frame["time_s"].max() - frame["time_s"].min()),
        "sampling_median_s": float(np.median(np.diff(np.sort(frame["time_s"].to_numpy(dtype=float))))),
    }
    for column in ("soc", "current_a", "voltage_v"):
        if column in frame.columns:
            values = frame[column].dropna()
            payload[f"{column}_min"] = float(values.min())
            payload[f"{column}_max"] = float(values.max())
    return payload


def soc_bucket_metrics(
    frame: pd.DataFrame,
    *,
    soc_column: str = "soc",
    residual_column: str = "residual_v",
    edges: Sequence[float] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
) -> pd.DataFrame:
    if soc_column not in frame.columns or residual_column not in frame.columns:
        raise MetricsError("SOC 或残差列缺失")
    rows: list[dict[str, Any]] = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (frame[soc_column] >= low) & (frame[soc_column] < high)
        if high == edges[-1]:
            mask |= frame[soc_column] == high
        samples = int(mask.sum())
        if samples == 0:
            rows.append(
                {
                    "soc_low": float(low),
                    "soc_high": float(high),
                    "points": 0,
                    "mae_mv": None,
                    "rmse_mv": None,
                    "max_absolute_error_mv": None,
                    "mean_error_mv": None,
                    "status": "NOT_VERIFIED",
                }
            )
            continue
        errors = frame.loc[mask, residual_column].to_numpy(dtype=float)
        rows.append(
            {
                "soc_low": float(low),
                "soc_high": float(high),
                "points": samples,
                "mae_mv": float(np.mean(np.abs(errors)) * 1000.0),
                "rmse_mv": float(np.sqrt(np.mean(errors**2)) * 1000.0),
                "max_absolute_error_mv": float(np.max(np.abs(errors)) * 1000.0),
                "mean_error_mv": float(np.mean(errors) * 1000.0),
                "status": "IDENTIFIED" if samples >= 20 else "INSUFFICIENT_DATA",
            }
        )
    return pd.DataFrame(rows)


def current_bucket_metrics(
    frame: pd.DataFrame,
    *,
    current_column: str = "current_a",
    residual_column: str = "residual_v",
    edges: Sequence[float] = (-3.0, -1.5, -0.5, 0.5, 1.5, 3.0, 5.0),
) -> pd.DataFrame:
    if current_column not in frame.columns or residual_column not in frame.columns:
        raise MetricsError("电流或残差列缺失")
    rows: list[dict[str, Any]] = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (frame[current_column] >= low) & (frame[current_column] < high)
        samples = int(mask.sum())
        rows.append(
            {
                "current_low_a": float(low),
                "current_high_a": float(high),
                "points": samples,
                "rmse_mv": float(np.sqrt(np.mean(frame.loc[mask, residual_column] ** 2)) * 1000.0)
                if samples
                else None,
                "status": "IDENTIFIED" if samples >= 20 else "NOT_VERIFIED",
            }
        )
    return pd.DataFrame(rows)


def improvement_percent(baseline_rmse_v: float, candidate_rmse_v: float) -> float | None:
    baseline = float(baseline_rmse_v)
    candidate = float(candidate_rmse_v)
    if baseline <= 0.0:
        return None
    return 100.0 * (baseline - candidate) / baseline

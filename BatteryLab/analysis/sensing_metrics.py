"""采集精度指标（Task 26）。"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from sensing.models import MeasurementResult


class MetricError(ValueError):
    """指标输入非法。"""


def _arrays(estimated: Sequence[float], reference: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    est = np.asarray(estimated, dtype=float)
    ref = np.asarray(reference, dtype=float)
    if est.shape != ref.shape:
        raise MetricError("估计值与参考值长度必须一致")
    if est.size == 0:
        raise MetricError("至少需要一个样本")
    if not np.isfinite(est).all() or not np.isfinite(ref).all():
        raise MetricError("指标计算不允许非有限值（无效样本应先剔除）")
    return est, ref


def measurement_errors(estimated: Sequence[float], reference: Sequence[float]) -> np.ndarray:
    est, ref = _arrays(estimated, reference)
    return est - ref


def compute_metrics(
    estimated: Sequence[float],
    reference: Sequence[float],
    *,
    unit: str,
    full_scale: float | None = None,
    full_scale_definition: str = "",
) -> dict[str, float | str | int]:
    errors = measurement_errors(estimated, reference)
    absolute = np.abs(errors)
    metrics: dict[str, float | str | int] = {
        "unit": unit,
        "count": int(errors.size),
        "mean_error": float(np.mean(errors)),
        "mae": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "max_abs_error": float(np.max(absolute)),
        "p95_abs_error": float(np.percentile(absolute, 95)),
        "error_std": float(np.std(errors, ddof=0)),
    }
    if full_scale is not None:
        if not math.isfinite(full_scale) or full_scale <= 0.0:
            raise MetricError("满量程必须为正")
        metrics["full_scale"] = float(full_scale)
        metrics["full_scale_definition"] = full_scale_definition or "explicit"
        metrics["full_scale_error_percent"] = float(np.max(absolute) / full_scale * 100.0)
    return metrics


def summarize_results(results: Sequence[MeasurementResult], unit: str) -> dict[str, float | int]:
    valid = [result for result in results if result.is_valid and result.estimated_value is not None and result.physical_input is not None]
    invalid = [result for result in results if not result.is_valid]
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
    estimated = [float(result.estimated_value) for result in valid]
    reference = [float(result.physical_input) for result in valid]
    if not valid:
        return {
            "valid_count": 0,
            "invalid_count": len(invalid),
            "saturation_ratio": 1.0,
            "status_counts": status_counts,
        }
    errors = np.array(estimated) - np.array(reference)
    return {
        "unit": unit,
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "saturation_ratio": float(status_counts.get("SATURATED", 0) / len(results)),
        "mean_error": float(np.mean(errors)),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "max_abs_error": float(np.max(np.abs(errors))),
        "p95_abs_error": float(np.percentile(np.abs(errors), 95)),
        "error_std": float(np.std(errors, ddof=0)),
        "status_counts": status_counts,
    }


def volt_to_mv(values: Sequence[float]) -> list[float]:
    return [float(value) * 1000.0 for value in values]


def amp_to_ma(values: Sequence[float]) -> list[float]:
    return [float(value) * 1000.0 for value in values]

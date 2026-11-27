"""电压残差分析：残差与时间、SOC、电流、电流变化量的关系。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analysis.fitting_metrics import MetricsError


def residual_correlations(frame: pd.DataFrame, *, residual_column: str = "residual_v") -> dict[str, Any]:
    required = {residual_column, "time_s", "current_a"}
    missing = required.difference(frame.columns)
    if missing:
        raise MetricsError(f"残差分析缺少列: {sorted(missing)}")
    residual = frame[residual_column].to_numpy(dtype=float)
    time_values = frame["time_s"].to_numpy(dtype=float)
    current = frame["current_a"].to_numpy(dtype=float)
    delta_current = np.concatenate([[0.0], np.diff(current)])
    payload: dict[str, Any] = {
        "points": int(residual.size),
        "mean_v": float(np.mean(residual)),
        "std_v": float(np.std(residual, ddof=1)) if residual.size > 1 else 0.0,
        "correlation_with_time": float(np.corrcoef(residual, time_values)[0, 1])
        if residual.size > 2 and np.std(time_values) > 0
        else None,
        "correlation_with_current": float(np.corrcoef(residual, current)[0, 1])
        if residual.size > 2 and np.std(current) > 0
        else None,
        "correlation_with_current_step": float(np.corrcoef(residual, delta_current)[0, 1])
        if residual.size > 2 and np.std(delta_current) > 0
        else None,
    }
    if "soc_reference" in frame.columns:
        soc = frame["soc_reference"].to_numpy(dtype=float)
        payload["correlation_with_soc"] = (
            float(np.corrcoef(residual, soc)[0, 1]) if np.std(soc) > 0 else None
        )
    else:
        payload["correlation_with_soc"] = None
    payload["persistent_bias"] = abs(payload["mean_v"]) > 0.01
    return payload


def worst_error_windows(
    frame: pd.DataFrame,
    *,
    window_points: int = 120,
    top_n: int = 5,
    residual_column: str = "residual_v",
) -> pd.DataFrame:
    if residual_column not in frame.columns:
        raise MetricsError("缺少残差列")
    residual = frame[residual_column].to_numpy(dtype=float)
    if residual.size < window_points:
        window_points = max(10, residual.size // 5)
    rolling = pd.Series(np.abs(residual)).rolling(window_points, min_periods=window_points).mean()
    order = np.argsort(rolling.to_numpy(dtype=float))[::-1]
    selected: list[int] = []
    for index in order:
        if not np.isfinite(rolling.iloc[index]):
            continue
        if all(abs(index - existing) > window_points for existing in selected):
            selected.append(int(index))
        if len(selected) >= top_n:
            break
    rows = []
    for index in selected:
        start = max(0, index - window_points)
        end = min(len(frame), index + 1)
        segment = frame.iloc[start:end]
        rows.append(
            {
                "window_start_s": float(segment["time_s"].iloc[0]),
                "window_end_s": float(segment["time_s"].iloc[-1]),
                "rolling_mean_abs_error_mv": float(np.mean(np.abs(segment[residual_column])) * 1000.0),
                "max_abs_error_mv": float(np.max(np.abs(segment[residual_column])) * 1000.0),
                "mean_current_a": float(segment["current_a"].mean()),
                "mean_soc": float(segment["soc_reference"].mean()) if "soc_reference" in segment else None,
            }
        )
    return pd.DataFrame(rows)


def steady_state_bias(frame: pd.DataFrame, *, current_tolerance_a: float = 0.05) -> dict[str, Any]:
    """静置/准静置区间的平均偏差，用于判断 OCV 曲线是否系统偏移。"""
    mask = frame["current_a"].abs() <= current_tolerance_a
    if mask.sum() < 10:
        return {"points": int(mask.sum()), "status": "NOT_VERIFIED"}
    values = frame.loc[mask, "residual_v"]
    return {
        "points": int(mask.sum()),
        "mean_bias_mv": float(values.mean() * 1000.0),
        "std_mv": float(values.std(ddof=1) * 1000.0),
        "status": "IDENTIFIED",
        "note": "静置偏差主要反映 OCV 曲线与样品差异，而不是动态 RC 参数误差。",
    }

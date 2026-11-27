"""健康状态统计指标（Task 26 / Task 27）。

只做数据汇总，不给出"综合 SOH"这类无依据的加权公式。容量型 SOH 与内阻
增长率分别报告；不同实验条件下的内阻不可直接比较。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np


class HealthMetricsError(ValueError):
    """健康指标输入非法。"""


def capacity_retention_percent(initial_capacity_ah: float, current_capacity_ah: float) -> float:
    if not all(math.isfinite(float(v)) for v in (initial_capacity_ah, current_capacity_ah)):
        raise HealthMetricsError("Invalid capacity")
    if float(initial_capacity_ah) <= 0.0 or float(current_capacity_ah) < 0.0:
        raise HealthMetricsError("Invalid capacity")
    return float(current_capacity_ah) / float(initial_capacity_ah) * 100.0


def equivalent_full_cycles(throughput_ah: Sequence[float], reference_capacity_ah: float) -> float:
    """累计吞吐量折算等效完整循环数。"""
    if float(reference_capacity_ah) <= 0.0:
        raise HealthMetricsError("Invalid reference capacity")
    values = np.asarray([float(v) for v in throughput_ah], dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0.0):
        raise HealthMetricsError("Invalid throughput")
    return float(np.sum(values) / float(reference_capacity_ah))


def summarize_capacity_series(
    cycle_index: Sequence[float],
    capacity_ah: Sequence[float],
) -> dict[str, Any]:
    """容量随循环的统计与线性衰减率（仅描述，不做 RUL 外推）。"""
    cycles = np.asarray([float(v) for v in cycle_index], dtype=float)
    capacity = np.asarray([float(v) for v in capacity_ah], dtype=float)
    if cycles.shape != capacity.shape or cycles.size == 0:
        raise HealthMetricsError("Invalid series")
    if not (np.isfinite(cycles).all() and np.isfinite(capacity).all()):
        raise HealthMetricsError("Invalid series")
    order = np.argsort(cycles)
    cycles = cycles[order]
    capacity = capacity[order]

    payload: dict[str, Any] = {
        "cycle_count": int(cycles.size),
        "initial_capacity_ah": float(capacity[0]),
        "final_capacity_ah": float(capacity[-1]),
        "minimum_capacity_ah": float(np.min(capacity)),
        "maximum_capacity_ah": float(np.max(capacity)),
        "retention_percent": capacity_retention_percent(capacity[0], capacity[-1]),
        "monotonic_decreasing": bool(np.all(np.diff(capacity) <= 0.0)),
    }
    if cycles.size >= 2 and np.ptp(cycles) > 0.0:
        slope, intercept = np.polyfit(cycles, capacity, 1)
        payload["linear_fade_ah_per_cycle"] = float(slope)
        payload["linear_fade_percent_per_100_cycles"] = (
            float(slope) * 100.0 / float(capacity[0]) * 100.0 if capacity[0] > 0 else None
        )
        payload["linear_fit_intercept_ah"] = float(intercept)
    else:
        payload["linear_fade_ah_per_cycle"] = None
        payload["linear_fade_percent_per_100_cycles"] = None
        payload["linear_fit_intercept_ah"] = None
    return payload


def summarize_resistance_series(
    cycle_index: Sequence[float],
    resistance_ohm: Sequence[float],
    reference_resistance_ohm: float,
) -> dict[str, Any]:
    """内阻增长统计；仅对同一电芯、相近条件的可比点使用。"""
    cycles = np.asarray([float(v) for v in cycle_index], dtype=float)
    resistance = np.asarray([float(v) for v in resistance_ohm], dtype=float)
    if cycles.shape != resistance.shape or cycles.size == 0:
        raise HealthMetricsError("Invalid series")
    if not (np.isfinite(cycles).all() and np.isfinite(resistance).all()):
        raise HealthMetricsError("Invalid series")
    if float(reference_resistance_ohm) <= 0.0:
        raise HealthMetricsError("Invalid reference resistance")
    growth = (resistance / float(reference_resistance_ohm) - 1.0) * 100.0
    return {
        "point_count": int(cycles.size),
        "reference_resistance_ohm": float(reference_resistance_ohm),
        "initial_resistance_ohm": float(resistance[0]),
        "final_resistance_ohm": float(resistance[-1]),
        "minimum_resistance_ohm": float(np.min(resistance)),
        "maximum_resistance_ohm": float(np.max(resistance)),
        "final_growth_percent": float(growth[-1]),
        "maximum_growth_percent": float(np.max(growth)),
        "growth_percent_series": [float(v) for v in growth],
    }


def data_quality_summary(statuses: Sequence[str]) -> dict[str, int]:
    """按状态统计循环/样本数量，用于 data_quality.json。"""
    summary: dict[str, int] = {}
    for status in statuses:
        key = str(status)
        summary[key] = summary.get(key, 0) + 1
    summary["total"] = len(statuses)
    return summary

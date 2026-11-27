"""完整放电容量积分与循环老化趋势（Task 25 / Task 26）。

积分约定：零阶保持 ``Q = Σ I_k·Δt_k / 3600``，电流单位为 A、时间 s、容量 Ah。

严格限制：

- 只对**满足协议起始状态与截止条件**的完整放电段称"完整容量"；
- 短时放电片段积分不能称为电池完整容量；
- 时间缺口超过 ``maximum_gap_s`` 直接报 ``DATA_GAP``，不跨越缺口积分；
- 若原始数据自带容量字段，程序重复积分再与之对比属于**容量计算一致性检查**，
  不能称为独立在线 SOH 估计精度。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from analysis.health_metrics import summarize_capacity_series
from health.capacity_soh import calculate_capacity_soh


class CycleAnalysisError(ValueError):
    """循环分析输入非法。"""


def integrate_discharge_capacity(
    time_s: Sequence[float],
    discharge_current_a: Sequence[float],
    maximum_gap_s: float,
) -> float:
    """零阶保持积分完整放电段容量（Ah）。"""
    t = np.asarray(time_s, dtype=float)
    i = np.asarray(discharge_current_a, dtype=float)
    if t.ndim != 1 or i.ndim != 1:
        raise CycleAnalysisError("Expected 1D arrays")
    if t.shape != i.shape or len(t) < 2:
        raise CycleAnalysisError("Invalid data size")
    if not (np.isfinite(t).all() and np.isfinite(i).all()):
        raise CycleAnalysisError("Invalid waveform")
    dt = np.diff(t)
    if np.any(dt <= 0.0):
        raise CycleAnalysisError("Invalid time axis")
    if float(maximum_gap_s) <= 0.0:
        raise CycleAnalysisError("Invalid gap limit")
    if np.any(dt > float(maximum_gap_s)):
        raise CycleAnalysisError("DATA_GAP")
    if np.any(i < 0.0):
        raise CycleAnalysisError("Expected discharge-only segment")
    capacity_ah = float(np.sum(i[:-1] * dt) / 3600.0)
    return capacity_ah


def build_cycle_table(
    cycles: Sequence[dict[str, Any]],
    reference_capacity_ah: float,
) -> list[dict[str, Any]]:
    """把循环记录整理为 Task 26 规定的输出字段，并计算容量型 SOH。"""
    if float(reference_capacity_ah) <= 0.0:
        raise CycleAnalysisError("基准容量必须为正")
    rows: list[dict[str, Any]] = []
    for record in cycles:
        capacity = float(record["discharge_capacity_ah"])
        health = calculate_capacity_soh(capacity, reference_capacity_ah)
        recorded = record.get("recorded_capacity_ah")
        integrated = record.get("integrated_capacity_ah", capacity)
        difference = None
        difference_percent = None
        if recorded is not None and math.isfinite(float(recorded)):
            difference = float(integrated) - float(recorded)
            if float(recorded) != 0.0:
                difference_percent = difference / float(recorded) * 100.0
        rows.append(
            {
                "cell_id": record.get("cell_id", "UNKNOWN"),
                "cycle_index": int(record["cycle_index"]),
                "discharge_capacity_ah": capacity,
                "reference_capacity_ah": float(reference_capacity_ah),
                "capacity_soh_percent": health.soh_percent,
                "capacity_loss_percent": health.capacity_loss_percent,
                "temperature_c": record.get("temperature_c"),
                "cutoff_voltage_v": record.get("cutoff_voltage_v"),
                "recorded_capacity_ah": None if recorded is None else float(recorded),
                "integrated_capacity_ah": float(integrated),
                "integrated_minus_recorded_ah": difference,
                "integrated_minus_recorded_percent": difference_percent,
                "data_quality_status": record.get("data_quality_status", "VALID"),
            }
        )
    return rows


def summarize_cycles(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """容量与 SOH 随循环的统计汇总。"""
    if not rows:
        raise CycleAnalysisError("空循环表")
    cycles = [float(row["cycle_index"]) for row in rows]
    capacities = [float(row["discharge_capacity_ah"]) for row in rows]
    summary = summarize_capacity_series(cycles, capacities)
    differences = [
        abs(float(row["integrated_minus_recorded_percent"]))
        for row in rows
        if row.get("integrated_minus_recorded_percent") is not None
    ]
    summary.update(
        {
            "cell_id": rows[0].get("cell_id", "UNKNOWN"),
            "reference_capacity_ah": float(rows[0]["reference_capacity_ah"]),
            "initial_soh_percent": float(rows[0]["capacity_soh_percent"]),
            "final_soh_percent": float(rows[-1]["capacity_soh_percent"]),
            "maximum_consistency_error_percent": max(differences) if differences else None,
            "consistency_checked_count": len(differences),
        }
    )
    return summary

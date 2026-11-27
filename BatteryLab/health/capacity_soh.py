"""容量型 SOH（Task 24）。

定义：``SOH_Q = Q_current / Q_reference × 100%``。

Q_reference 优先采用**同一电芯早期、条件可比的完整容量实验**。若使用了不同
电芯、不同温度或不同倍率，必须在记录中显式标注，不能直接视为老化。

SOH 可能因容量测试差异暂时超过 100%，禁止裁剪为 100% 隐藏原始数据，也不强制
所有循环的 SOH 单调下降。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class SOHValidationError(ValueError):
    """SOH 输入非法。"""


@dataclass(frozen=True)
class CapacityHealth:
    current_capacity_ah: float
    reference_capacity_ah: float
    soh_percent: float
    capacity_loss_percent: float


def calculate_capacity_soh(
    current_capacity_ah: float,
    reference_capacity_ah: float,
) -> CapacityHealth:
    if not all(math.isfinite(float(v)) for v in (current_capacity_ah, reference_capacity_ah)):
        raise SOHValidationError("Invalid capacity")
    if float(current_capacity_ah) < 0.0:
        raise SOHValidationError("Invalid current capacity")
    if float(reference_capacity_ah) <= 0.0:
        raise SOHValidationError("Invalid reference capacity")
    soh = float(current_capacity_ah) / float(reference_capacity_ah) * 100.0
    return CapacityHealth(
        current_capacity_ah=float(current_capacity_ah),
        reference_capacity_ah=float(reference_capacity_ah),
        soh_percent=float(soh),
        capacity_loss_percent=float(100.0 - soh),
    )


def build_capacity_soh_table(
    current_capacities_ah: list[float],
    reference_capacity_ah: float,
) -> list[dict[str, float | int]]:
    """逐循环计算 SOH，保留原始容量与原始 SOH（不做平滑以外的修改）。"""
    rows: list[dict[str, float | int]] = []
    for index, capacity in enumerate(current_capacities_ah):
        health = calculate_capacity_soh(capacity, reference_capacity_ah)
        rows.append(
            {
                "cycle_index": int(index + 1),
                "current_capacity_ah": health.current_capacity_ah,
                "reference_capacity_ah": health.reference_capacity_ah,
                "soh_percent": health.soh_percent,
                "capacity_loss_percent": health.capacity_loss_percent,
            }
        )
    return rows

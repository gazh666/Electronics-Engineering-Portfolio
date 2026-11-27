"""内阻健康指标（Task 27）。

``R_app = -ΔV / ΔI``（脉冲法），增长率：

``growth = (R_current / R_reference - 1) × 100%``

可比性前提（缺一不可）：同一电芯、相近 SOC、相近温度、相同电流方向、相近
脉冲幅值、相同取样时间窗口、相同松弛与实验条件。任一不满足即标记
``CONDITION_MISMATCH``，不得把差异归因于老化。

必须区分：瞬时欧姆内阻、指定窗口 DCIR、ECM 拟合 R0、EIS 阻抗。这些量不能
直接互相替代。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class ResistanceHealthError(ValueError):
    """内阻健康输入非法。"""


def resistance_growth_percent(
    current_resistance_ohm: float,
    reference_resistance_ohm: float,
) -> float:
    if not all(
        math.isfinite(float(v)) for v in (current_resistance_ohm, reference_resistance_ohm)
    ):
        raise ResistanceHealthError("Invalid resistance")
    if min(float(current_resistance_ohm), float(reference_resistance_ohm)) <= 0.0:
        raise ResistanceHealthError("Invalid resistance")
    return (float(current_resistance_ohm) / float(reference_resistance_ohm) - 1.0) * 100.0


def pulse_resistance_ohm(
    voltage_before_v: float,
    voltage_after_v: float,
    current_before_a: float,
    current_after_a: float,
) -> float:
    """脉冲法表观内阻 ``R = -ΔV/ΔI``（放电为正，压降为负）。"""
    values = (voltage_before_v, voltage_after_v, current_before_a, current_after_a)
    if not all(math.isfinite(float(v)) for v in values):
        raise ResistanceHealthError("Invalid pulse data")
    delta_i = float(current_after_a) - float(current_before_a)
    if abs(delta_i) <= 1.0e-9:
        raise ResistanceHealthError("电流变化过小，无法计算内阻")
    return -(float(voltage_after_v) - float(voltage_before_v)) / delta_i


@dataclass(frozen=True)
class ResistanceCondition:
    cell_id: str
    soc: float
    temperature_c: float
    current_direction: str
    pulse_amplitude_a: float
    window_s: float
    method: str = "dcir"


def compare_resistance_conditions(
    reference: ResistanceCondition,
    current: ResistanceCondition,
    *,
    maximum_soc_difference: float = 0.05,
    maximum_temperature_difference_c: float = 2.0,
    maximum_amplitude_relative_difference: float = 0.10,
    maximum_window_relative_difference: float = 0.10,
) -> dict[str, object]:
    """检查两点内阻是否可比；不可比时返回 CONDITION_MISMATCH 及原因。"""
    reasons: list[str] = []
    if reference.cell_id != current.cell_id:
        reasons.append("DIFFERENT_CELL")
    if abs(float(reference.soc) - float(current.soc)) > float(maximum_soc_difference):
        reasons.append("SOC_MISMATCH")
    if abs(float(reference.temperature_c) - float(current.temperature_c)) > float(
        maximum_temperature_difference_c
    ):
        reasons.append("TEMPERATURE_MISMATCH")
    if reference.current_direction != current.current_direction:
        reasons.append("DIRECTION_MISMATCH")
    if reference.method != current.method:
        reasons.append("METHOD_MISMATCH")
    if abs(float(reference.pulse_amplitude_a)) > 0.0:
        relative = abs(
            (float(current.pulse_amplitude_a) - float(reference.pulse_amplitude_a))
            / float(reference.pulse_amplitude_a)
        )
        if relative > float(maximum_amplitude_relative_difference):
            reasons.append("AMPLITUDE_MISMATCH")
    if abs(float(reference.window_s)) > 0.0:
        relative = abs(
            (float(current.window_s) - float(reference.window_s)) / float(reference.window_s)
        )
        if relative > float(maximum_window_relative_difference):
            reasons.append("WINDOW_MISMATCH")
    return {
        "status": "COMPARABLE" if not reasons else "CONDITION_MISMATCH",
        "reasons": reasons,
        "comparable": not reasons,
    }

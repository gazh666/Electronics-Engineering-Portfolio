"""抗积分饱和：限幅与反计算（back-calculation）辅助函数。

反计算抗饱和与"积分器裁剪"不是同一个东西：反计算把执行器饱和量反馈到积分器
输入，使积分状态主动回退，而不是简单把积分值截断到区间。
"""

from __future__ import annotations

import math


def clamp(value: float, lower: float, upper: float) -> float:
    if not all(math.isfinite(v) for v in (value, lower, upper)):
        raise ValueError("Non-finite clamp input")
    if lower > upper:
        raise ValueError("Invalid limits")
    return min(max(value, lower), upper)


def back_calculation_term(
    kaw: float,
    saturated: float,
    unsaturated: float,
) -> float:
    """反计算修正项 ``Kaw * (u_sat - u_raw)``，饱和时把积分往回收。"""
    if not all(math.isfinite(v) for v in (kaw, saturated, unsaturated)):
        raise ValueError("Non-finite anti-windup input")
    if kaw < 0.0:
        raise ValueError("Negative anti-windup gain")
    return kaw * (saturated - unsaturated)


def integral_rate(
    ki: float,
    error: float,
    kaw: float,
    saturated: float,
    unsaturated: float,
) -> float:
    """积分变化率 ``Ki*e + Kaw*(u_sat - u_raw)``。"""
    return ki * error + back_calculation_term(kaw, saturated, unsaturated)


def is_frozen(unsaturated: float, saturated: float, error: float) -> bool:
    """条件积分冻结判据。

    仅当饱和方向与误差方向相同（继续积分会加深饱和）时冻结；
    误差反向时允许积分退出饱和。
    """
    if not all(math.isfinite(v) for v in (unsaturated, saturated, error)):
        raise ValueError("Non-finite freeze input")
    if unsaturated > saturated and error > 0.0:
        return True
    if unsaturated < saturated and error < 0.0:
        return True
    return False


def conditional_integral_rate(
    ki: float,
    error: float,
    kaw: float,
    saturated: float,
    unsaturated: float,
) -> float:
    """条件积分 + 反计算。

    冻结时积分输入置零，避免反计算项在恒流段把电流指令长期拉低；
    未冻结时保留反计算项，帮助从饱和快速退出。
    """
    if is_frozen(unsaturated, saturated, error):
        return 0.0
    return integral_rate(ki, error, kaw, saturated, unsaturated)


def is_stable_timestep(kaw: float, dt_s: float) -> bool:
    """反计算显式离散的稳定性粗检：``Kaw * dt < 2``。"""
    if not math.isfinite(kaw) or not math.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError("Invalid timestep data")
    return kaw * dt_s < 2.0

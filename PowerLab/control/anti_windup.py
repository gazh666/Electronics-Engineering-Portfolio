"""抗积分饱和策略：无抗饱和、条件积分、反算抗饱和。

三种模式都只作用于积分状态增量，不修改已记录的真实波形。
"""

from __future__ import annotations

import math

from circuits.validators import finite_number, positive_number

EPS = 1e-9


def clamp_duty(raw_duty: float, duty_min: float, duty_max: float) -> float:
    """占空比限幅。"""
    raw = finite_number(raw_duty, "raw_duty")
    low = finite_number(duty_min, "duty_min")
    high = finite_number(duty_max, "duty_max")
    if not (0.0 <= low < high <= 1.0):
        raise ValueError("duty limits must satisfy 0 <= min < max <= 1")
    return max(low, min(high, raw))


def back_calculation_correction(
    tracking_gain: float, limited_duty: float, raw_duty: float
) -> float:
    """反算抗饱和校正项 Kaw × (D - D_raw)。"""
    gain = positive_number(tracking_gain, "tracking_gain")
    limited = finite_number(limited_duty, "limited_duty")
    raw = finite_number(raw_duty, "raw_duty")
    return gain * (limited - raw)


def conditional_integral_weight(
    raw_duty: float,
    error_v: float,
    duty_min: float,
    duty_max: float,
) -> float:
    """条件积分权重：饱和方向禁止继续累积，反向误差仍可退饱和。

    未饱和时返回 1；上限饱和且误差为正返回 0；下限饱和且误差为负返回 0。
    """
    raw = finite_number(raw_duty, "raw_duty")
    error = finite_number(error_v, "error_v")
    low = finite_number(duty_min, "duty_min")
    high = finite_number(duty_max, "duty_max")
    if raw >= high - EPS and error > 0:
        return 0.0
    if raw <= low + EPS and error < 0:
        return 0.0
    return 1.0


def integral_increment(
    method: str,
    *,
    ki: float,
    error_v: float,
    dt_s: float,
    raw_duty: float,
    limited_duty: float,
    duty_min: float,
    duty_max: float,
    tracking_gain: float,
) -> tuple[float, float]:
    """返回 ``(积分增量, 抗饱和校正量)``。

    - ``none``：dI = Ki × e × dt。
    - ``conditional``：按条件积分权重缩放误差项。
    - ``back_calculation``：dI = (Ki × e + Kaw × (D - D_raw)) × dt。
    """
    dt = positive_number(dt_s, "dt_s")
    gain = finite_number(ki, "ki")
    if gain < 0:
        raise ValueError("ki must be nonnegative")
    error = finite_number(error_v, "error_v")
    raw = finite_number(raw_duty, "raw_duty")
    limited = finite_number(limited_duty, "limited_duty")

    if method == "none":
        return gain * error * dt, 0.0
    if method == "conditional":
        weight = conditional_integral_weight(raw, error, duty_min, duty_max)
        return gain * error * weight * dt, 0.0
    if method == "back_calculation":
        correction = back_calculation_correction(tracking_gain, limited, raw)
        return (gain * error + correction) * dt, correction
    raise ValueError(f"unknown anti-windup method {method!r}")


def saturation_direction(raw_duty: float, duty_min: float, duty_max: float) -> str:
    """返回 ``high`` / ``low`` / ``none``。"""
    raw = finite_number(raw_duty, "raw_duty")
    if raw > duty_max + EPS:
        return "high"
    if raw < duty_min - EPS:
        return "low"
    return "none"


def is_finite(value: float) -> bool:
    return math.isfinite(float(value))

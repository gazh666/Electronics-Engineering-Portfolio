"""一阶稳态热估算。

边界：
- 只做 Tj ≈ Ta + P × Rθ 的一阶估算；
- Rθ 的适用条件（铜箔面积、层数、气流）必须与数据手册测试条件一致；
- 不是热仿真，也不是温升实测。
"""

from __future__ import annotations

import math

# BQ24610 数据手册 SLUS892D §10.2.1.2.4 明确写到：
# "MOSFET rDS(on) increases by 50% with 100ºC junction temperature rise"。
# 这里把它作为一阶线性近似系数使用，仅用于教学级降额估算。
DEFAULT_RDS_ON_TEMPCO_PER_C = 0.005


def estimate_junction_temperature(
    ambient_temperature_c: float,
    power_loss_w: float,
    thermal_resistance_c_per_w: float,
) -> dict:
    """一阶稳态结温估算。"""
    values = [ambient_temperature_c, power_loss_w, thermal_resistance_c_per_w]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid thermal input")
    if power_loss_w < 0:
        raise ValueError("Invalid power")
    if thermal_resistance_c_per_w <= 0:
        raise ValueError("Invalid thermal resistance")

    temperature_rise = power_loss_w * thermal_resistance_c_per_w

    return {
        "estimated_temperature_rise_c": temperature_rise,
        "estimated_junction_temperature_c": ambient_temperature_c + temperature_rise,
    }


def estimate_rds_on_at_temperature(
    rds_on_25c_ohm: float,
    junction_temperature_c: float,
    tempco_per_c: float = DEFAULT_RDS_ON_TEMPCO_PER_C,
) -> dict:
    """把 25℃ 的 RDS(on) 线性外推到给定结温。

    这是线性近似，高温段实际曲线通常是超线性的，因此该值偏乐观，
    只能用于初筛，不能替代数据手册曲线。
    """
    r25 = rds_on_25c_ohm
    if not math.isfinite(r25) or r25 <= 0:
        raise ValueError("Invalid RDS(on)")
    if not math.isfinite(junction_temperature_c):
        raise ValueError("Invalid junction temperature")
    if not math.isfinite(tempco_per_c) or tempco_per_c < 0:
        raise ValueError("Invalid tempco")

    factor = 1.0 + tempco_per_c * (junction_temperature_c - 25.0)
    return {
        "rds_on_ohm": r25 * factor,
        "scale_factor": factor,
        "tempco_per_c": tempco_per_c,
    }


def estimate_parallel_thermal_resistance(
    thermal_resistances_c_per_w: list[float],
) -> dict:
    """多个等温散热路径并联时的等效热阻（教学用，忽略热耦合）。"""
    values = [v for v in thermal_resistances_c_per_w]
    if not values or not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError("Invalid thermal resistance list")

    equivalent = 1.0 / sum(1.0 / v for v in values)

    return {
        "equivalent_thermal_resistance_c_per_w": equivalent,
        "path_count": len(values),
    }

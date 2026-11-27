"""反馈分压与标准阻值选择。

BQ24610 (SLUS892D p.17, Equation 1)：
    V_BAT = 2.1 V × (1 + R2/R1)
其中 R2 接 VFB 到电池，R1 接 VFB 到 GND。

本模块不内置任何"常见参考电压"默认值：调用方必须显式传入数据手册基准。
"""

from __future__ import annotations

import math

E96_SERIES = (
    100, 102, 105, 107, 110, 113, 115, 118, 121, 124, 127, 130,
    133, 137, 140, 143, 147, 150, 154, 158, 162, 165, 169, 174,
    178, 182, 187, 191, 196, 200, 205, 210, 215, 221, 226, 232,
    237, 243, 249, 255, 261, 267, 274, 280, 287, 294, 301, 309,
    316, 324, 332, 340, 348, 357, 365, 374, 383, 392, 402, 412,
    422, 432, 442, 453, 464, 475, 487, 499, 511, 523, 536, 549,
    562, 576, 590, 604, 619, 634, 649, 665, 681, 698, 715, 732,
    750, 768, 787, 806, 825, 845, 866, 887, 909, 931, 953, 976,
)


def calculate_feedback_divider(
    target_voltage_v: float,
    reference_voltage_v: float,
    lower_resistance_ohm: float,
) -> dict:
    """由目标电压与基准电压反算上臂电阻。"""
    values = [target_voltage_v, reference_voltage_v, lower_resistance_ohm]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid parameter")
    if not (target_voltage_v > reference_voltage_v > 0):
        raise ValueError("Invalid voltage")
    if lower_resistance_ohm <= 0:
        raise ValueError("Invalid resistance")

    upper = (target_voltage_v / reference_voltage_v - 1.0) * lower_resistance_ohm
    divider_current = target_voltage_v / (upper + lower_resistance_ohm)

    return {
        "upper_resistance_ohm": upper,
        "lower_resistance_ohm": lower_resistance_ohm,
        "divider_current_a": divider_current,
    }


def calculate_actual_feedback_voltage(
    reference_voltage_v: float,
    upper_resistance_ohm: float,
    lower_resistance_ohm: float,
) -> float:
    """由实际电阻回算实际设定电压。"""
    values = [reference_voltage_v, upper_resistance_ohm, lower_resistance_ohm]
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError("Invalid parameter")

    return reference_voltage_v * (1.0 + upper_resistance_ohm / lower_resistance_ohm)


def nearest_e96(value_ohm: float) -> float:
    """把阻值映射到最近的 E96 值（按数量级缩放）。"""
    if not math.isfinite(value_ohm) or value_ohm <= 0:
        raise ValueError("Invalid resistance")

    decade = 10 ** math.floor(math.log10(value_ohm))
    normalized = value_ohm / decade

    nearest = min(E96_SERIES, key=lambda s: abs(s - normalized * 100.0))
    return nearest / 100.0 * decade


def calculate_divider_error_budget(
    reference_voltage_v: float,
    reference_tolerance_percent: float,
    upper_resistance_ohm: float,
    lower_resistance_ohm: float,
    resistor_tolerance_percent: float,
    vfb_bias_current_a: float = 0.0,
) -> dict:
    """最坏情况设定偏差的解析预算（不含温漂实测）。"""
    if reference_tolerance_percent < 0 or resistor_tolerance_percent < 0:
        raise ValueError("Invalid tolerance")
    if vfb_bias_current_a < 0:
        raise ValueError("Invalid bias current")

    nominal = calculate_actual_feedback_voltage(
        reference_voltage_v, upper_resistance_ohm, lower_resistance_ohm
    )

    ref_low = reference_voltage_v * (1.0 - reference_tolerance_percent / 100.0)
    ref_high = reference_voltage_v * (1.0 + reference_tolerance_percent / 100.0)
    r_low = 1.0 - resistor_tolerance_percent / 100.0
    r_high = 1.0 + resistor_tolerance_percent / 100.0

    # 最低输出电压：基准偏低、上臂偏小、下臂偏大
    worst_low = ref_low * (1.0 + upper_resistance_ohm * r_low / (lower_resistance_ohm * r_high))
    # 最高输出电压：基准偏高、上臂偏大、下臂偏小
    worst_high = ref_high * (1.0 + upper_resistance_ohm * r_high / (lower_resistance_ohm * r_low))

    # 偏置电流在下臂上产生的附加压降
    bias_effect = vfb_bias_current_a * lower_resistance_ohm

    return {
        "nominal_voltage_v": nominal,
        "worst_case_low_v": worst_low,
        "worst_case_high_v": worst_high,
        "worst_case_span_v": worst_high - worst_low,
        "vfb_bias_effect_v": bias_effect,
        "worst_case_low_with_bias_v": worst_low - bias_effect,
    }


def calculate_bq24610_charge_current(
    iset_voltage_v: float,
    sense_resistance_ohm: float,
) -> float:
    """BQ24610 快速充电电流：I_CHG = V_ISET1 / (20 × R_SR)（SLUS892D p.17）。"""
    if not math.isfinite(iset_voltage_v) or iset_voltage_v < 0:
        raise ValueError("Invalid ISET voltage")
    if not math.isfinite(sense_resistance_ohm) or sense_resistance_ohm <= 0:
        raise ValueError("Invalid sense resistance")

    return iset_voltage_v / (20.0 * sense_resistance_ohm)


def calculate_bq24610_precharge_current(
    iset2_voltage_v: float,
    sense_resistance_ohm: float,
) -> float:
    """BQ24610 预充/终止电流：I = V_ISET2 / (100 × R_SR)（SLUS892D p.17-18）。"""
    if not math.isfinite(iset2_voltage_v) or iset2_voltage_v < 0:
        raise ValueError("Invalid ISET2 voltage")
    if not math.isfinite(sense_resistance_ohm) or sense_resistance_ohm <= 0:
        raise ValueError("Invalid sense resistance")

    return iset2_voltage_v / (100.0 * sense_resistance_ohm)


def calculate_bq24610_adapter_current(
    acset_voltage_v: float,
    sense_resistance_ohm: float,
) -> float:
    """BQ24610 输入限流：I_AC = V_ACSET / (20 × R_AC)（SLUS892D p.17）。"""
    if not math.isfinite(acset_voltage_v) or acset_voltage_v < 0:
        raise ValueError("Invalid ACSET voltage")
    if not math.isfinite(sense_resistance_ohm) or sense_resistance_ohm <= 0:
        raise ValueError("Invalid sense resistance")

    return acset_voltage_v / (20.0 * sense_resistance_ohm)


def calculate_iset_divider(
    reference_voltage_v: float,
    target_iset_voltage_v: float,
    lower_resistance_ohm: float,
) -> dict:
    """由 VREF 分压得到 ISET/ACSET 设定电压的上臂电阻。"""
    if not (reference_voltage_v > target_iset_voltage_v > 0):
        raise ValueError("Invalid ISET divider voltage")
    if lower_resistance_ohm <= 0:
        raise ValueError("Invalid resistance")

    ratio = target_iset_voltage_v / reference_voltage_v
    upper = lower_resistance_ohm * (1.0 - ratio) / ratio

    return {
        "upper_resistance_ohm": upper,
        "ratio": ratio,
        "divider_current_a": reference_voltage_v / (upper + lower_resistance_ohm),
    }

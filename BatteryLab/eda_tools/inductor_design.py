"""Buck 电感初步估算（理想 CCM，连续导通模式）。

边界：
- 不含磁芯损耗、不含 DCR 压降对占空比的修正；
- 饱和电流与温升电流定义不同，不能把标称电流当峰值上限；
- 正式设计需扫描输入电压与电池电压全范围。
"""

from __future__ import annotations

import math


def calculate_buck_inductor(
    input_voltage_v: float,
    output_voltage_v: float,
    output_current_a: float,
    switching_frequency_hz: float,
    ripple_ratio: float,
) -> dict:
    """由纹波比例反算所需电感量。"""
    values = [
        input_voltage_v,
        output_voltage_v,
        output_current_a,
        switching_frequency_hz,
        ripple_ratio,
    ]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid input")
    if not (0 < output_voltage_v < input_voltage_v):
        raise ValueError("Invalid buck voltage")
    if min(output_current_a, switching_frequency_hz, ripple_ratio) <= 0:
        raise ValueError("Invalid parameter")

    duty = output_voltage_v / input_voltage_v
    ripple = ripple_ratio * output_current_a
    inductance = (input_voltage_v - output_voltage_v) * duty / (switching_frequency_hz * ripple)

    peak_current = output_current_a + ripple / 2.0
    rms_current = math.sqrt(output_current_a ** 2 + ripple ** 2 / 12.0)

    return {
        "ideal_duty": duty,
        "required_inductance_h": inductance,
        "estimated_ripple_a": ripple,
        "estimated_peak_current_a": peak_current,
        "estimated_rms_current_a": rms_current,
    }


def calculate_ripple_for_inductance(
    input_voltage_v: float,
    output_voltage_v: float,
    inductance_h: float,
    switching_frequency_hz: float,
) -> dict:
    """给定实际电感量后回算纹波与峰值电流。"""
    values = [input_voltage_v, output_voltage_v, inductance_h, switching_frequency_hz]
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError("Invalid parameter")
    if output_voltage_v >= input_voltage_v:
        raise ValueError("Invalid buck voltage")

    duty = output_voltage_v / input_voltage_v
    ripple = (input_voltage_v - output_voltage_v) * duty / (switching_frequency_hz * inductance_h)

    return {
        "ideal_duty": duty,
        "estimated_ripple_a": ripple,
        "duty_off_s": (1.0 - duty) / switching_frequency_hz,
    }


def calculate_lc_resonance(
    inductance_h: float,
    capacitance_f: float,
) -> float:
    """输出 LC 谐振频率。BQ24610 内部补偿要求约 12–17 kHz（SLUS892D p.30）。"""
    if not (math.isfinite(inductance_h) and inductance_h > 0):
        raise ValueError("Invalid inductance")
    if not (math.isfinite(capacitance_f) and capacitance_f > 0):
        raise ValueError("Invalid capacitance")

    return 1.0 / (2.0 * math.pi * math.sqrt(inductance_h * capacitance_f))


def estimate_inductor_dc_loss(
    dc_resistance_ohm: float,
    rms_current_a: float,
) -> dict:
    """电感 DCR 直流铜损（不含磁芯损耗）。"""
    if not (math.isfinite(dc_resistance_ohm) and dc_resistance_ohm > 0):
        raise ValueError("Invalid DCR")
    if not (math.isfinite(rms_current_a) and rms_current_a >= 0):
        raise ValueError("Invalid current")

    return {
        "dc_loss_w": rms_current_a ** 2 * dc_resistance_ohm,
        "dc_voltage_drop_v": rms_current_a * dc_resistance_ohm,
    }

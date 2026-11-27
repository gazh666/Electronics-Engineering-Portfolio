"""双向电流编码/解码与分流电阻工程量。

约定：放电电流为正，充电电流为负。
Vout = Vref + G * I * Rshunt；I = (Vout - Vref) / (G * Rshunt)。
"""

from __future__ import annotations

import math


class CurrentDecodeError(ValueError):
    """电流解码输入非法。"""


def _real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CurrentDecodeError(f"{name} 必须是有限数值")
    return float(value)


def shunt_voltage(current_a: float, shunt_ohm: float) -> float:
    shunt = _real(shunt_ohm, "分流电阻")
    if shunt <= 0.0:
        raise CurrentDecodeError("分流电阻必须为正")
    return _real(current_a, "电流") * shunt


def shunt_power(current_a: float, shunt_ohm: float) -> float:
    shunt = _real(shunt_ohm, "分流电阻")
    if shunt <= 0.0:
        raise CurrentDecodeError("分流电阻必须为正")
    current = _real(current_a, "电流")
    return current * current * shunt


def amplifier_output(current_a: float, *, gain: float, shunt_ohm: float, reference_v: float) -> float:
    gain_value = _real(gain, "放大倍数")
    if gain_value <= 0.0:
        raise CurrentDecodeError("放大倍数必须为正")
    return _real(reference_v, "零点参考") + gain_value * shunt_voltage(current_a, shunt_ohm)


def current_from_output(output_v: float, *, gain: float, shunt_ohm: float, reference_v: float) -> float:
    gain_value = _real(gain, "放大倍数")
    shunt = _real(shunt_ohm, "分流电阻")
    if gain_value <= 0.0 or shunt <= 0.0:
        raise CurrentDecodeError("放大倍数与分流电阻必须为正")
    return (_real(output_v, "输出电压") - _real(reference_v, "零点参考")) / (gain_value * shunt)


def current_resolution_a(*, gain: float, shunt_ohm: float, lsb_v: float) -> float:
    gain_value = _real(gain, "放大倍数")
    shunt = _real(shunt_ohm, "分流电阻")
    if gain_value <= 0.0 or shunt <= 0.0:
        raise CurrentDecodeError("放大倍数与分流电阻必须为正")
    return _real(lsb_v, "LSB") / (gain_value * shunt)


def offset_referred_current_a(offset_v: float, shunt_ohm: float) -> float:
    """把放大器输入失调折算为输入电流误差。"""
    shunt = _real(shunt_ohm, "分流电阻")
    if shunt <= 0.0:
        raise CurrentDecodeError("分流电阻必须为正")
    return _real(offset_v, "输入失调") / shunt


def full_scale_output_range(*, gain: float, shunt_ohm: float, reference_v: float, current_limit_a: float) -> tuple[float, float]:
    limit = abs(_real(current_limit_a, "电流限值"))
    return (
        amplifier_output(-limit, gain=gain, shunt_ohm=shunt_ohm, reference_v=reference_v),
        amplifier_output(limit, gain=gain, shunt_ohm=shunt_ohm, reference_v=reference_v),
    )

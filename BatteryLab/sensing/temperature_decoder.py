"""NTC 温度模型与分压解码（Task 21/22/23）。

采用 NTC 接地、固定电阻上拉的比率式分压拓扑：

    Rntc(T) = R25 * exp(B * (1/T - 1/T25))
    Vntc    = Vexc * Rntc / (Rpullup + Rntc)
    Rntc    = Rpullup * Vntc / (Vexc - Vntc)
    T       = 1 / (1/T25 + ln(Rntc/R25)/B)
"""

from __future__ import annotations

import math

T25_K = 298.15
ZERO_CELSIUS_K = 273.15


class TemperatureDecodeError(ValueError):
    """温度模型输入非法或不可反演。"""


def _real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise TemperatureDecodeError(f"{name} 必须是有限数值")
    return float(value)


def ntc_resistance(
    temperature_c: float,
    *,
    r25_ohm: float = 10000.0,
    beta_k: float = 3950.0,
    t25_c: float = 25.0,
) -> float:
    r25 = _real(r25_ohm, "R25")
    beta = _real(beta_k, "B 值")
    if r25 <= 0.0:
        raise TemperatureDecodeError("R25 必须为正")
    if beta <= 0.0:
        raise TemperatureDecodeError("B 值必须为正")
    temperature_k = _real(temperature_c, "温度") + ZERO_CELSIUS_K
    if temperature_k <= 0.0:
        raise TemperatureDecodeError("绝对温度必须为正")
    t25_k = _real(t25_c, "参考温度") + ZERO_CELSIUS_K
    if t25_k <= 0.0:
        raise TemperatureDecodeError("参考绝对温度必须为正")
    return r25 * math.exp(beta * (1.0 / temperature_k - 1.0 / t25_k))


def ntc_temperature(
    resistance_ohm: float,
    *,
    r25_ohm: float = 10000.0,
    beta_k: float = 3950.0,
    t25_c: float = 25.0,
) -> float:
    r25 = _real(r25_ohm, "R25")
    beta = _real(beta_k, "B 值")
    resistance = _real(resistance_ohm, "NTC 电阻")
    if r25 <= 0.0 or beta <= 0.0:
        raise TemperatureDecodeError("R25 与 B 值必须为正")
    if resistance <= 0.0:
        raise TemperatureDecodeError("NTC 电阻必须为正")
    t25_k = _real(t25_c, "参考温度") + ZERO_CELSIUS_K
    temperature_k = 1.0 / (1.0 / t25_k + math.log(resistance / r25) / beta)
    if temperature_k <= 0.0:
        raise TemperatureDecodeError("反演得到的绝对温度非正")
    return temperature_k - ZERO_CELSIUS_K


def divider_voltage(
    resistance_ohm: float,
    *,
    pullup_ohm: float = 10000.0,
    excitation_v: float = 3.3,
) -> float:
    pullup = _real(pullup_ohm, "上拉电阻")
    excitation = _real(excitation_v, "激励电压")
    resistance = _real(resistance_ohm, "NTC 电阻")
    if pullup <= 0.0 or excitation <= 0.0 or resistance < 0.0:
        raise TemperatureDecodeError("分压参数非法")
    return excitation * resistance / (pullup + resistance)


def resistance_from_voltage(
    voltage_v: float,
    *,
    pullup_ohm: float = 10000.0,
    excitation_v: float = 3.3,
    tolerance_v: float = 1e-9,
) -> float:
    pullup = _real(pullup_ohm, "上拉电阻")
    excitation = _real(excitation_v, "激励电压")
    voltage = _real(voltage_v, "NTC 分压")
    if pullup <= 0.0 or excitation <= 0.0:
        raise TemperatureDecodeError("分压参数非法")
    if voltage <= tolerance_v:
        raise TemperatureDecodeError("分压接近 0（疑似 NTC 短路），无法反演")
    if voltage >= excitation - tolerance_v:
        raise TemperatureDecodeError("分压接近激励电压（疑似 NTC 开路），无法反演")
    return pullup * voltage / (excitation - voltage)


def temperature_from_voltage(
    voltage_v: float,
    *,
    r25_ohm: float = 10000.0,
    beta_k: float = 3950.0,
    pullup_ohm: float = 10000.0,
    excitation_v: float = 3.3,
) -> float:
    resistance = resistance_from_voltage(voltage_v, pullup_ohm=pullup_ohm, excitation_v=excitation_v)
    return ntc_temperature(resistance, r25_ohm=r25_ohm, beta_k=beta_k)


def voltage_sensitivity_v_per_c(
    temperature_c: float,
    *,
    r25_ohm: float = 10000.0,
    beta_k: float = 3950.0,
    pullup_ohm: float = 10000.0,
    excitation_v: float = 3.3,
    delta_c: float = 0.01,
) -> float:
    """用中心差分估计 dV/dT（V/℃）。"""
    upper = divider_voltage(
        ntc_resistance(temperature_c + delta_c, r25_ohm=r25_ohm, beta_k=beta_k),
        pullup_ohm=pullup_ohm,
        excitation_v=excitation_v,
    )
    lower = divider_voltage(
        ntc_resistance(temperature_c - delta_c, r25_ohm=r25_ohm, beta_k=beta_k),
        pullup_ohm=pullup_ohm,
        excitation_v=excitation_v,
    )
    return (upper - lower) / (2.0 * delta_c)


def ntc_power_w(
    temperature_c: float,
    *,
    r25_ohm: float = 10000.0,
    beta_k: float = 3950.0,
    pullup_ohm: float = 10000.0,
    excitation_v: float = 3.3,
) -> float:
    resistance = ntc_resistance(temperature_c, r25_ohm=r25_ohm, beta_k=beta_k)
    voltage = divider_voltage(resistance, pullup_ohm=pullup_ohm, excitation_v=excitation_v)
    return voltage * voltage / resistance

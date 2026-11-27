"""一阶 RC 等效电路模型。

Vterminal = OCV - I * R0 - V1
dV1/dt = -V1/(R1*C1) + I/C1
"""

from __future__ import annotations

import math

from battery_models.states import StateError, update_polarization_voltage


class FirstOrderRcError(ValueError):
    """一阶 RC 参数非法。"""


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise FirstOrderRcError(f"{name} 不允许使用布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FirstOrderRcError(f"{name} 必须是数值") from exc
    if not math.isfinite(number):
        raise FirstOrderRcError(f"{name} 必须是有限数值")
    return number


def calculate_time_constant(r1_ohm: float, c1_f: float) -> float:
    resistance = _finite(r1_ohm, "R1")
    capacitance = _finite(c1_f, "C1")
    if resistance <= 0.0 or capacitance <= 0.0:
        raise FirstOrderRcError("R1 与 C1 必须为正数")
    return resistance * capacitance


def update_first_order_polarization(
    previous_voltage_v: float,
    current_a: float,
    r1_ohm: float,
    c1_f: float,
    dt_s: float,
) -> float:
    """复用统一精确离散更新，避免重复实现。"""
    try:
        return update_polarization_voltage(previous_voltage_v, current_a, r1_ohm, c1_f, dt_s)
    except StateError as exc:
        raise FirstOrderRcError(str(exc)) from exc


def first_order_terminal_voltage(
    ocv_v: float,
    current_a: float,
    r0_ohm: float,
    polarization_1_v: float,
) -> float:
    ocv = _finite(ocv_v, "OCV")
    current = _finite(current_a, "电流")
    resistance = _finite(r0_ohm, "R0")
    polarization = _finite(polarization_1_v, "V1")
    if resistance < 0.0:
        raise FirstOrderRcError("R0 必须为零或正数")
    return ocv - current * resistance - polarization


def calculate_polarization_loss(polarization_1_v: float, r1_ohm: float) -> float:
    """第一极化电阻损耗 = V1^2 / R1。"""
    voltage = _finite(polarization_1_v, "V1")
    resistance = _finite(r1_ohm, "R1")
    if resistance <= 0.0:
        raise FirstOrderRcError("R1 必须为正数")
    return voltage**2 / resistance


def calculate_stored_energy(c1_f: float, polarization_1_v: float) -> float:
    """第一 RC 电容储能 = 0.5 * C1 * V1^2。"""
    capacitance = _finite(c1_f, "C1")
    voltage = _finite(polarization_1_v, "V1")
    if capacitance <= 0.0:
        raise FirstOrderRcError("C1 必须为正数")
    return 0.5 * capacitance * voltage**2


def polarization_fraction(elapsed_s: float, tau_s: float, *, charging: bool = True) -> float:
    """理论极化比例：建立 ``1-exp(-t/tau)``，恢复 ``exp(-t/tau)``。"""
    elapsed = _finite(elapsed_s, "经过时间")
    tau = _finite(tau_s, "时间常数")
    if elapsed < 0.0:
        raise FirstOrderRcError("经过时间不能为负")
    if tau <= 0.0:
        raise FirstOrderRcError("时间常数必须为正")
    decay = math.exp(-elapsed / tau)
    return 1.0 - decay if charging else decay

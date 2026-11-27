"""二阶 RC 等效电路模型。

两个 RC 支路在等效电路中依次串联：
Vterminal = OCV - I*R0 - V1 - V2
dV1/dt = -V1/(R1*C1) + I/C1
dV2/dt = -V2/(R2*C2) + I/C2
"""

from __future__ import annotations

import math

from battery_models.states import update_polarization_voltage


class SecondOrderRcError(ValueError):
    """二阶 RC 参数非法。"""


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise SecondOrderRcError(f"{name} 不允许使用布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SecondOrderRcError(f"{name} 必须是数值") from exc
    if not math.isfinite(number):
        raise SecondOrderRcError(f"{name} 必须是有限数值")
    return number


def calculate_time_constants(r1_ohm: float, c1_f: float, r2_ohm: float, c2_f: float) -> tuple[float, float]:
    values = [_finite(r1_ohm, "R1"), _finite(c1_f, "C1"), _finite(r2_ohm, "R2"), _finite(c2_f, "C2")]
    if any(value <= 0.0 for value in values):
        raise SecondOrderRcError("RC 电阻与电容必须为正数")
    return values[0] * values[1], values[2] * values[3]


def update_second_order_polarization(
    previous_1_v: float,
    previous_2_v: float,
    current_a: float,
    r1_ohm: float,
    c1_f: float,
    r2_ohm: float,
    c2_f: float,
    dt_s: float,
) -> tuple[float, float]:
    """两个支路分别调用同一精确更新函数。"""
    return (
        update_polarization_voltage(previous_1_v, current_a, r1_ohm, c1_f, dt_s),
        update_polarization_voltage(previous_2_v, current_a, r2_ohm, c2_f, dt_s),
    )


def second_order_terminal_voltage(
    ocv_v: float,
    current_a: float,
    r0_ohm: float,
    polarization_1_v: float,
    polarization_2_v: float,
) -> float:
    ocv = _finite(ocv_v, "OCV")
    current = _finite(current_a, "电流")
    resistance = _finite(r0_ohm, "R0")
    if resistance < 0.0:
        raise SecondOrderRcError("R0 必须为零或正数")
    return ocv - current * resistance - _finite(polarization_1_v, "V1") - _finite(polarization_2_v, "V2")


def calculate_polarization_losses(
    r1_ohm: float,
    polarization_1_v: float,
    r2_ohm: float,
    polarization_2_v: float,
) -> tuple[float, float]:
    """各极化电阻损耗 = Vj^2 / Rj。"""
    r1 = _finite(r1_ohm, "R1")
    r2 = _finite(r2_ohm, "R2")
    if r1 <= 0.0 or r2 <= 0.0:
        raise SecondOrderRcError("R1 与 R2 必须为正数")
    return _finite(polarization_1_v, "V1") ** 2 / r1, _finite(polarization_2_v, "V2") ** 2 / r2


def calculate_stored_energies(
    c1_f: float,
    polarization_1_v: float,
    c2_f: float,
    polarization_2_v: float,
) -> tuple[float, float]:
    c1 = _finite(c1_f, "C1")
    c2 = _finite(c2_f, "C2")
    if c1 <= 0.0 or c2 <= 0.0:
        raise SecondOrderRcError("C1 与 C2 必须为正数")
    return 0.5 * c1 * _finite(polarization_1_v, "V1") ** 2, 0.5 * c2 * _finite(polarization_2_v, "V2") ** 2

"""Rint 电池模型：OCV 电压源串联欧姆内阻。

Vterminal = OCV - I * R0，Pohmic = I^2 * R0。
放电电流为正，充电电流为负。
"""

from __future__ import annotations

import math
from typing import Any, Iterable


class RintError(ValueError):
    """Rint 计算参数非法。"""


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise RintError(f"{name} 不允许使用布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RintError(f"{name} 必须是数值") from exc
    if not math.isfinite(number):
        raise RintError(f"{name} 必须是有限数值")
    return number


def calculate_rint_voltage(ocv_v: float, current_a: float, r0_ohm: float) -> float:
    """端电压 = OCV - I * R0。"""
    ocv = _finite(ocv_v, "OCV")
    current = _finite(current_a, "电流")
    resistance = _finite(r0_ohm, "欧姆内阻")
    if resistance < 0.0:
        raise RintError("欧姆内阻必须为零或正数")
    return ocv - current * resistance


def calculate_ohmic_loss(current_a: float, r0_ohm: float) -> float:
    """欧姆内阻损耗 = I^2 * R0。"""
    current = _finite(current_a, "电流")
    resistance = _finite(r0_ohm, "欧姆内阻")
    if resistance < 0.0:
        raise RintError("欧姆内阻必须为零或正数")
    return current**2 * resistance


def calculate_ohmic_drop(current_a: float, r0_ohm: float) -> float:
    """欧姆压降 = I * R0（放电为正）。"""
    current = _finite(current_a, "电流")
    resistance = _finite(r0_ohm, "欧姆内阻")
    if resistance < 0.0:
        raise RintError("欧姆内阻必须为零或正数")
    return current * resistance


def rint_benchmark_rows(
    *,
    ocv_v: float = 3.8,
    r0_ohm: float = 0.03,
    currents_a: Iterable[float] = (0.0, 0.5, 1.0, 2.0, 3.0, -0.5, -1.0),
) -> list[dict[str, Any]]:
    """恒定 OCV 下的 Rint 电流扫描结果（程序实际计算，不是硬编码表）。"""
    rows: list[dict[str, Any]] = []
    for current in currents_a:
        current_value = _finite(current, "电流")
        rows.append(
            {
                "current_a": current_value,
                "ocv_v": float(ocv_v),
                "ohmic_drop_v": calculate_ohmic_drop(current_value, r0_ohm),
                "terminal_voltage_v": calculate_rint_voltage(ocv_v, current_value, r0_ohm),
                "ohmic_loss_w": calculate_ohmic_loss(current_value, r0_ohm),
                "mode": "discharge" if current_value > 0 else ("charge" if current_value < 0 else "rest"),
            }
        )
    return rows

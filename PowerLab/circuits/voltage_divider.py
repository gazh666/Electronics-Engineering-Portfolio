"""电阻分压电路（第二阶段统一入口）。

本模块复用第一阶段已验证的 :mod:`circuits.divider`，并补充直流扫描相关的
派生量，避免重复实现同一拓扑。
"""

from __future__ import annotations

from .divider import (
    build_voltage_divider,
    theoretical_current,
    theoretical_output_voltage,
)
from .validators import positive_number

__all__ = [
    "build_voltage_divider",
    "theoretical_output_voltage",
    "theoretical_current",
    "divider_transfer_slope",
]


def divider_transfer_slope(r1_ohm: float, r2_ohm: float) -> float:
    """分压器直流传递斜率 ``dVout/dVin = R2 / (R1 + R2)``。"""
    r1 = positive_number(r1_ohm, "r1_ohm")
    r2 = positive_number(r2_ohm, "r2_ohm")
    return r2 / (r1 + r2)

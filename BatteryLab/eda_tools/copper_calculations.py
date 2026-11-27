"""理想均匀铜箔的直流电阻、压降与损耗。

边界：
- 不含过孔、焊点、连接器、铜箔缩颈、电流拥挤、温度空间分布与高频效应；
- 不能用来证明实际 PCB 温升符合要求；
- 载流能力需要 IPC-2152 类研究或实测，本模块不提供载流保证。
"""

from __future__ import annotations

import math

RHO_20_CU = 1.724e-8
ALPHA_CU = 0.00393


def calculate_copper_trace(
    length_mm: float,
    width_mm: float,
    thickness_um: float,
    current_a: float,
    temperature_c: float = 20.0,
) -> dict:
    """均匀矩形铜箔的直流参数。"""
    values = [length_mm, width_mm, thickness_um, current_a, temperature_c]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid input")
    if min(length_mm, width_mm, thickness_um) <= 0:
        raise ValueError("Invalid geometry")

    rho = RHO_20_CU * (1.0 + ALPHA_CU * (temperature_c - 20.0))
    if rho <= 0:
        raise ValueError("Temperature model out of range")

    length_m = length_mm * 1e-3
    area_m2 = width_mm * 1e-3 * thickness_um * 1e-6

    resistance = rho * length_m / area_m2

    return {
        "resistance_ohm": resistance,
        "voltage_drop_v": current_a * resistance,
        "power_loss_w": current_a ** 2 * resistance,
        "resistivity_ohm_m": rho,
        "cross_section_mm2": width_mm * thickness_um * 1e-3,
    }


def calculate_via_bundle_resistance(
    via_count: int,
    via_barrel_diameter_mm: float,
    plating_thickness_um: float,
    board_thickness_mm: float,
    temperature_c: float = 20.0,
) -> dict:
    """过孔束的直流电阻估算（仅镀铜筒，不含焊盘扩散电阻）。"""
    if via_count <= 0:
        raise ValueError("Invalid via count")
    if min(via_barrel_diameter_mm, plating_thickness_um, board_thickness_mm) <= 0:
        raise ValueError("Invalid via geometry")

    rho = RHO_20_CU * (1.0 + ALPHA_CU * (temperature_c - 20.0))
    circumference = math.pi * via_barrel_diameter_mm * 1e-3
    area_m2 = circumference * plating_thickness_um * 1e-6
    single = rho * board_thickness_mm * 1e-3 / area_m2

    return {
        "single_via_resistance_ohm": single,
        "bundle_resistance_ohm": single / via_count,
        "paralell_via_count": via_count,
    }

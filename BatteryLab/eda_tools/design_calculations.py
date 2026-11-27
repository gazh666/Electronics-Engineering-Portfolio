"""基础硬件设计计算。

所有函数只做解析计算（欧姆定律、一阶 RC、功率分配），不包含热仿真、
不包含器件实测数据、不构成量产保证。
"""

from __future__ import annotations

import math


def positive(name: str, value: float) -> float:
    """校验有限正数。"""
    if not math.isfinite(value):
        raise ValueError(f"{name}: non-finite")
    if value <= 0:
        raise ValueError(f"{name}: must be positive")
    return value


def calculate_shunt(
    current_a: float,
    resistance_ohm: float,
    rated_power_w: float,
) -> dict:
    """分流电阻压降、功耗与标称功率占比。

    注意：nominal_power_limit_pass 只代表在给定额定功率下的直流功耗检查，
    不代表温升降额、脉冲耐量或短路耐受已满足。
    """
    if not math.isfinite(current_a):
        raise ValueError("Invalid current")

    r = positive("resistance_ohm", resistance_ohm)
    rated = positive("rated_power_w", rated_power_w)

    voltage = current_a * r
    power = current_a ** 2 * r

    return {
        "voltage_drop_v": voltage,
        "power_loss_w": power,
        "nominal_power_utilization_percent": power / rated * 100.0,
        "nominal_power_limit_pass": power <= rated,
        "absolute_voltage_drop_v": abs(voltage),
    }


def calculate_differential_rc(
    resistance_high_ohm: float,
    resistance_low_ohm: float,
    capacitance_f: float,
    interference_frequency_hz: float,
) -> dict:
    """差分 RC 的一阶截止频率与单频衰减。

    tau = (R_high + R_low) * C，适用于两根输入支路各自串阻、差分并容的结构。
    """
    r_high = positive("resistance_high", resistance_high_ohm)
    r_low = positive("resistance_low", resistance_low_ohm)
    c = positive("capacitance", capacitance_f)
    f = positive("frequency", interference_frequency_hz)

    tau = (r_high + r_low) * c
    fc = 1.0 / (2.0 * math.pi * tau)

    attenuation_db = -10.0 * math.log10(1.0 + (f / fc) ** 2)

    return {
        "time_constant_s": tau,
        "cutoff_frequency_hz": fc,
        "attenuation_db": attenuation_db,
        "settling_time_1_percent_s": -math.log(0.01) * tau,
        "rise_time_10_90_s": math.log(9.0) * tau,
    }


def calculate_mosfet_path(
    current_rms_a: float,
    resistances_ohm: list[float],
) -> dict:
    """串联功率路径（例如背靠背 MOSFET）的导通损耗。"""
    if not math.isfinite(current_rms_a):
        raise ValueError("Invalid current")
    if current_rms_a < 0:
        raise ValueError("Invalid RMS current")

    resistances = [positive("Rds_on", r) for r in resistances_ohm]
    if not resistances:
        raise ValueError("Missing MOSFETs")

    total_r = sum(resistances)

    return {
        "path_resistance_ohm": total_r,
        "rms_voltage_drop_v": current_rms_a * total_r,
        "total_conduction_loss_w": current_rms_a ** 2 * total_r,
        "individual_losses_w": [current_rms_a ** 2 * r for r in resistances],
    }


def calculate_balancing_branch(
    cell_voltage_v: float,
    balance_resistance_ohm: float,
    switch_resistance_ohm: float,
) -> dict:
    """被动均衡支路电流与电阻/开关功耗。"""
    v = positive("cell_voltage", cell_voltage_v)
    r = positive("balance_resistance", balance_resistance_ohm)

    if not math.isfinite(switch_resistance_ohm) or switch_resistance_ohm < 0:
        raise ValueError("Invalid switch resistance")

    current = v / (r + switch_resistance_ohm)

    return {
        "balancing_current_a": current,
        "resistor_power_w": current ** 2 * r,
        "switch_power_w": current ** 2 * switch_resistance_ohm,
        "equivalent_resistance_ohm": r + switch_resistance_ohm,
    }


def calculate_balancing_duration(
    cell_capacity_ah: float,
    delta_soc: float,
    balancing_current_a: float,
) -> dict:
    """把需要转移的容量折算成均衡时间（理想恒流，无自放电）。"""
    cap = positive("cell_capacity_ah", cell_capacity_ah)
    current = positive("balancing_current_a", balancing_current_a)

    if not math.isfinite(delta_soc) or delta_soc < 0:
        raise ValueError("Invalid delta_soc")

    charge_ah = cap * delta_soc
    seconds = charge_ah / current * 3600.0

    return {
        "charge_to_remove_ah": charge_ah,
        "balancing_time_s": seconds,
        "balancing_time_h": seconds / 3600.0,
    }


def calculate_shunt_scale(
    resistance_ohm: float,
    sense_full_scale_v: float,
    adc_lsb_v: float,
) -> dict:
    """分流电阻量程与电流分辨率（用于比较 1/2/5/10 mΩ 候选）。

    这里的分辨率是 ADC 量化步距折算值，不是测量精度。
    """
    r = positive("resistance_ohm", resistance_ohm)
    vfs = positive("sense_full_scale_v", sense_full_scale_v)
    lsb = positive("adc_lsb_v", adc_lsb_v)

    return {
        "full_scale_current_a": vfs / r,
        "current_lsb_a": lsb / r,
        "shunt_power_at_full_scale_w": (vfs / r) ** 2 * r,
    }

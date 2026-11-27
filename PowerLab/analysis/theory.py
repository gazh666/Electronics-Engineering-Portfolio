"""基础电路理论计算。

所有函数都是解析公式计算，返回的数值必须标记为
:data:`DATA_SOURCE` = ``analytical_theory``，与 ``spice_simulation`` 严格区分。
函数本身不读取、不生成任何 SPICE 数据。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from circuits.validators import (
    finite_number,
    nonnegative_number,
    positive_number,
    temperature_celsius,
)

DATA_SOURCE = "analytical_theory"

BOLTZMANN_J_PER_K = 1.380649e-23
ELEMENTARY_CHARGE_C = 1.602176634e-19
ABSOLUTE_ZERO_C = 273.15
DIODE_EXPONENT_LIMIT = 700.0


def _return_scalar_or_array(array: np.ndarray, scalar_input: bool) -> float | np.ndarray:
    if scalar_input:
        return float(array)
    return array


def _finite_array(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        raise ValueError(f"{name} must not be empty")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains NaN or Infinity")
    return array


def theory_result(
    quantity: str,
    value: Any,
    unit: str,
    *,
    inputs: dict[str, Any] | None = None,
    formula: str = "",
) -> dict[str, Any]:
    """把理论数值包装成带来源标记的结果字典。"""
    return {
        "data_source": DATA_SOURCE,
        "quantity": quantity,
        "value": value,
        "unit": unit,
        "inputs": dict(inputs or {}),
        "formula": formula,
    }


# ---------------------------------------------------------------- 电阻分压
def voltage_divider_voltage(vin_v: float, r1_ohm: float, r2_ohm: float) -> float:
    """Vout = Vin × R2 / (R1 + R2)，单位 V。"""
    vin = finite_number(vin_v, "vin_v")
    r1 = positive_number(r1_ohm, "r1_ohm")
    r2 = positive_number(r2_ohm, "r2_ohm")
    return vin * r2 / (r1 + r2)


def voltage_divider_current(vin_v: float, r1_ohm: float, r2_ohm: float) -> float:
    """I = Vin / (R1 + R2)，单位 A。"""
    vin = finite_number(vin_v, "vin_v")
    r1 = positive_number(r1_ohm, "r1_ohm")
    r2 = positive_number(r2_ohm, "r2_ohm")
    return vin / (r1 + r2)


# ---------------------------------------------------------------------- RC
def rc_time_constant(r_ohm: float, c_f: float) -> float:
    """tau = R × C，单位 s。"""
    return positive_number(r_ohm, "r_ohm") * positive_number(c_f, "c_f")


def rc_charging_voltage(
    time_s: Any,
    input_v: float,
    r_ohm: float,
    c_f: float,
) -> float | np.ndarray:
    """零初始电压充电：Vc(t) = Vin × (1 − exp(−t/tau))，单位 V。"""
    time = _finite_array(time_s, "time_s")
    if np.any(time < 0):
        raise ValueError("time_s must be nonnegative")
    scalar = np.isscalar(time_s)
    vin = finite_number(input_v, "input_v")
    tau = rc_time_constant(r_ohm, c_f)
    result = vin * (1.0 - np.exp(-time / tau))
    return _return_scalar_or_array(result, scalar)


def rc_discharging_voltage(
    time_s: Any,
    initial_v: float,
    r_ohm: float,
    c_f: float,
) -> float | np.ndarray:
    """放电：Vc(t) = Vinitial × exp(−t/tau)，单位 V。

    ``initial_v`` 应使用实际开始放电时的电压，而不是假设一定充满到输入电压。
    """
    time = _finite_array(time_s, "time_s")
    if np.any(time < 0):
        raise ValueError("time_s must be nonnegative")
    scalar = np.isscalar(time_s)
    initial = finite_number(initial_v, "initial_v")
    tau = rc_time_constant(r_ohm, c_f)
    result = initial * np.exp(-time / tau)
    return _return_scalar_or_array(result, scalar)


def rc_cutoff_frequency(r_ohm: float, c_f: float) -> float:
    """fc = 1 / (2πRC)，单位 Hz。"""
    tau = rc_time_constant(r_ohm, c_f)
    return 1.0 / (2.0 * math.pi * tau)


def rc_frequency_response(
    frequency_hz: Any,
    r_ohm: float,
    c_f: float,
) -> dict[str, Any]:
    """RC 低通理论传递函数 H(jω) = 1 / (1 + jωRC)。"""
    frequency = _finite_array(frequency_hz, "frequency_hz")
    if np.any(frequency <= 0):
        raise ValueError("frequency_hz must be positive")
    tau = rc_time_constant(r_ohm, c_f)
    omega = 2.0 * math.pi * frequency
    transfer = 1.0 / (1.0 + 1j * omega * tau)
    magnitude = np.abs(transfer)
    gain_db = np.full(magnitude.shape, -np.inf)
    positive = magnitude > 0
    gain_db[positive] = 20.0 * np.log10(magnitude[positive])
    return {
        "data_source": DATA_SOURCE,
        "frequency_hz": frequency,
        "transfer": transfer,
        "magnitude": magnitude,
        "gain_db": gain_db,
        "phase_deg": np.angle(transfer, deg=True),
        "formula": "H(jw) = 1 / (1 + jwRC)",
    }


# ---------------------------------------------------------------------- RL
def rl_time_constant(l_h: float, r_ohm: float) -> float:
    """tau = L / R，单位 s。"""
    return positive_number(l_h, "l_h") / positive_number(r_ohm, "r_ohm")


def rl_step_current(
    time_s: Any,
    input_v: float,
    r_ohm: float,
    l_h: float,
) -> float | np.ndarray:
    """RL 阶跃电流：I(t) = (Vin/R) × (1 − exp(−t/tau))，单位 A。"""
    time = _finite_array(time_s, "time_s")
    if np.any(time < 0):
        raise ValueError("time_s must be nonnegative")
    scalar = np.isscalar(time_s)
    vin = finite_number(input_v, "input_v")
    resistance = positive_number(r_ohm, "r_ohm")
    tau = rl_time_constant(l_h, resistance)
    final_current = vin / resistance
    result = final_current * (1.0 - np.exp(-time / tau))
    return _return_scalar_or_array(result, scalar)


def inductor_stored_energy(l_h: float, current_a: float) -> float:
    """电感储能 E = 0.5 × L × I²，单位 J。"""
    inductance = positive_number(l_h, "l_h")
    current = finite_number(current_a, "current_a")
    return 0.5 * inductance * current * current


def capacitor_stored_energy(c_f: float, voltage_v: float) -> float:
    """电容储能 E = 0.5 × C × V²，单位 J。"""
    capacitance = positive_number(c_f, "c_f")
    voltage = finite_number(voltage_v, "voltage_v")
    return 0.5 * capacitance * voltage * voltage


# --------------------------------------------------------------------- RLC
def rlc_natural_frequency(l_h: float, c_f: float) -> float:
    """f0 = 1 / (2π√(LC))，单位 Hz。"""
    inductance = positive_number(l_h, "l_h")
    capacitance = positive_number(c_f, "c_f")
    return 1.0 / (2.0 * math.pi * math.sqrt(inductance * capacitance))


def rlc_alpha(r_ohm: float, l_h: float) -> float:
    """阻尼系数 alpha = R / (2L)，单位 1/s。"""
    return positive_number(r_ohm, "r_ohm") / (2.0 * positive_number(l_h, "l_h"))


def rlc_damping_ratio(r_ohm: float, l_h: float, c_f: float) -> float:
    """阻尼比 zeta = (R/2) × √(C/L)，无量纲。"""
    resistance = positive_number(r_ohm, "r_ohm")
    inductance = positive_number(l_h, "l_h")
    capacitance = positive_number(c_f, "c_f")
    return 0.5 * resistance * math.sqrt(capacitance / inductance)


def rlc_quality_factor(r_ohm: float, l_h: float, c_f: float) -> float:
    """品质因数 Q = (1/R) × √(L/C)，无量纲。"""
    resistance = positive_number(r_ohm, "r_ohm")
    inductance = positive_number(l_h, "l_h")
    capacitance = positive_number(c_f, "c_f")
    return math.sqrt(inductance / capacitance) / resistance


def rlc_critical_resistance(l_h: float, c_f: float) -> float:
    """临界阻尼电阻 Rcrit = 2√(L/C)，单位 Ω。"""
    inductance = positive_number(l_h, "l_h")
    capacitance = positive_number(c_f, "c_f")
    return 2.0 * math.sqrt(inductance / capacitance)


def rlc_frequency_response(
    frequency_hz: Any,
    r_ohm: float,
    l_h: float,
    c_f: float,
) -> dict[str, Any]:
    """串联 RLC 电容电压传递函数 H(jω) = 1 / (1 − ω²LC + jωRC)。"""
    frequency = _finite_array(frequency_hz, "frequency_hz")
    if np.any(frequency <= 0):
        raise ValueError("frequency_hz must be positive")
    resistance = positive_number(r_ohm, "r_ohm")
    inductance = positive_number(l_h, "l_h")
    capacitance = positive_number(c_f, "c_f")
    omega = 2.0 * math.pi * frequency
    denominator = (1.0 - omega**2 * inductance * capacitance) + 1j * omega * resistance * capacitance
    transfer = 1.0 / denominator
    magnitude = np.abs(transfer)
    gain_db = np.full(magnitude.shape, -np.inf)
    positive = magnitude > 0
    gain_db[positive] = 20.0 * np.log10(magnitude[positive])
    return {
        "data_source": DATA_SOURCE,
        "frequency_hz": frequency,
        "transfer": transfer,
        "magnitude": magnitude,
        "gain_db": gain_db,
        "phase_deg": np.angle(transfer, deg=True),
        "formula": "H(jw) = 1 / (1 - w^2 LC + jwRC)",
    }


def rlc_peak_frequency(r_ohm: float, l_h: float, c_f: float) -> float | None:
    """电容电压幅值峰值频率 ``f0√(1−2ζ²)``；``ζ ≥ 1/√2`` 时无内部峰值。"""
    zeta = rlc_damping_ratio(r_ohm, l_h, c_f)
    if zeta >= 1.0 / math.sqrt(2.0):
        return None
    return rlc_natural_frequency(l_h, c_f) * math.sqrt(1.0 - 2.0 * zeta**2)


def rlc_damped_frequency(r_ohm: float, l_h: float, c_f: float) -> float | None:
    """欠阻尼振荡频率 ``fd = f0√(1−ζ²)``；``ζ ≥ 1`` 时返回 ``None``。"""
    zeta = rlc_damping_ratio(r_ohm, l_h, c_f)
    if zeta >= 1.0:
        return None
    return rlc_natural_frequency(l_h, c_f) * math.sqrt(1.0 - zeta**2)


def rlc_step_overshoot_percent(r_ohm: float, l_h: float, c_f: float) -> float:
    """阶跃响应理论过冲百分比 ``100 × exp(−πζ/√(1−ζ²))``；过阻尼返回 0。"""
    zeta = rlc_damping_ratio(r_ohm, l_h, c_f)
    if zeta >= 1.0:
        return 0.0
    return 100.0 * math.exp(-math.pi * zeta / math.sqrt(1.0 - zeta**2))


# ------------------------------------------------------------------- 二极管
def diode_thermal_voltage(temperature_c: float = 25.0) -> float:
    """热电压 Vt = kT/q，单位 V。"""
    temperature_c = temperature_celsius(temperature_c)
    temperature_k = temperature_c + ABSOLUTE_ZERO_C
    return BOLTZMANN_J_PER_K * temperature_k / ELEMENTARY_CHARGE_C


def diode_ideal_current(
    v_diode_v: Any,
    saturation_current_a: float = 1e-9,
    ideality_factor: float = 1.8,
    temperature_c: float = 25.0,
) -> float | np.ndarray:
    """Shockley 方程（不含串联电阻）I = Is × [exp(Vd/(nVt)) − 1]，单位 A。

    该式使用理想结电压；存在 RS 时不能直接用外部端电压代入并要求与 SPICE 完全一致。
    """
    voltage = _finite_array(v_diode_v, "v_diode_v")
    scalar = np.isscalar(v_diode_v)
    is_current = positive_number(saturation_current_a, "saturation_current_a")
    ideality = positive_number(ideality_factor, "ideality_factor")
    thermal = diode_thermal_voltage(temperature_c)
    exponent = np.clip(voltage / (ideality * thermal), -DIODE_EXPONENT_LIMIT, DIODE_EXPONENT_LIMIT)
    result = is_current * np.expm1(exponent)
    return _return_scalar_or_array(result, scalar)


# ------------------------------------------------------------------- 半波整流
def half_wave_average_voltage(peak_v: float) -> float:
    """理想半波整流平均电压 Vavg = Vpeak / π，单位 V。"""
    return positive_number(peak_v, "peak_v") / math.pi


def half_wave_rms_voltage(peak_v: float) -> float:
    """理想半波整流有效值 Vrms = Vpeak / 2，单位 V。"""
    return positive_number(peak_v, "peak_v") / 2.0


def half_wave_load_power(peak_v: float, load_ohm: float) -> float:
    """理想半波整流负载平均功率 P = Vrms² / R = Vpeak² / (4R)，单位 W。"""
    peak = positive_number(peak_v, "peak_v")
    load = positive_number(load_ohm, "load_ohm")
    return peak**2 / (4.0 * load)


def half_wave_theory(peak_v: float, load_ohm: float) -> dict[str, Any]:
    """理想半波整流理论汇总（带 analytical_theory 标记）。"""
    peak = positive_number(peak_v, "peak_v")
    load = positive_number(load_ohm, "load_ohm")
    return {
        "data_source": DATA_SOURCE,
        "peak_v": peak,
        "average_voltage_v": half_wave_average_voltage(peak),
        "rms_voltage_v": half_wave_rms_voltage(peak),
        "average_load_power_w": half_wave_load_power(peak, load),
        "formula": "Vavg = Vpeak/pi; Vrms = Vpeak/2; Pavg = Vpeak^2/(4R)",
    }

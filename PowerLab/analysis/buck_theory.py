"""理想 Buck 变换器理论计算（仅用于参数设计与对照）。

所有结果都是 ``analytical_theory``，不是 SPICE 仿真结果。
理想 CCM 公式假设：
- 开关与二极管无损耗；
- 电感、电容无寄生参数；
- 输出电压无纹波、负载为恒阻；
- 电感电流连续且没有反向电流。

实际非同步 Buck 存在开关导通电阻与二极管正向压降，实际输出会低于
``D * Vin``；轻载进入 DCM 后，理想 CCM 关系不再适用。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from circuits.buck_config import BuckConfig
from circuits.validators import finite_number, positive_number

DATA_SOURCE = "analytical_theory"


@dataclass(frozen=True)
class BuckTheoryResult:
    """理想 CCM 理论结果（SI 单位）。"""

    period_s: float
    duty_cycle: float
    on_time_s: float
    off_time_s: float
    ideal_output_voltage_v: float
    ideal_output_current_a: float
    inductor_ripple_app: float
    inductor_peak_current_a: float
    inductor_valley_current_a: float
    capacitor_ripple_vpp: float
    boundary_current_a: float
    boundary_resistance_ohm: float
    ccm_assumption_valid: bool
    data_source: str = DATA_SOURCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_s": self.period_s,
            "duty_cycle": self.duty_cycle,
            "on_time_s": self.on_time_s,
            "off_time_s": self.off_time_s,
            "ideal_output_voltage_v": self.ideal_output_voltage_v,
            "ideal_output_current_a": self.ideal_output_current_a,
            "inductor_ripple_app": self.inductor_ripple_app,
            "inductor_peak_current_a": self.inductor_peak_current_a,
            "inductor_valley_current_a": self.inductor_valley_current_a,
            "capacitor_ripple_vpp": self.capacitor_ripple_vpp,
            "boundary_current_a": self.boundary_current_a,
            "boundary_resistance_ohm": self.boundary_resistance_ohm,
            "ccm_assumption_valid": self.ccm_assumption_valid,
            "data_source": self.data_source,
            "assumptions": "ideal switches, ideal diode, lossless L/C, CCM, constant resistive load",
        }


@dataclass(frozen=True)
class DcmTheoryResult:
    """理想 DCM 变换比理论结果（仅在该假设成立时作为对照）。"""

    k: float
    conversion_ratio: float
    output_voltage_v: float
    dcm_assumption_valid: bool
    boundary_k: float
    data_source: str = DATA_SOURCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "k": self.k,
            "conversion_ratio": self.conversion_ratio,
            "output_voltage_v": self.output_voltage_v,
            "dcm_assumption_valid": self.dcm_assumption_valid,
            "boundary_k": self.boundary_k,
            "data_source": self.data_source,
            "assumption": "ideal DCM: M = 2 / (1 + sqrt(1 + 4K/D^2)), K = 2L/(R*T)",
        }


def calculate_ideal_buck(config: BuckConfig) -> BuckTheoryResult:
    """计算理想 CCM 下的周期、占空比、纹波与临界负载。"""
    if not isinstance(config, BuckConfig):
        raise ValueError("config must be BuckConfig")

    vin = config.input_voltage_v
    duty = config.duty_cycle
    frequency = config.switching_frequency_hz
    inductance = config.inductance_h
    capacitance = config.capacitance_f

    period = 1.0 / frequency
    vout = vin * duty
    iout = vout / config.load_resistance_ohm

    ripple_i = (vin - vout) * duty / (inductance * frequency)
    boundary_i = ripple_i / 2.0
    peak = iout + boundary_i
    valley = iout - boundary_i
    ripple_v = ripple_i / (8.0 * frequency * capacitance)

    return BuckTheoryResult(
        period_s=period,
        duty_cycle=duty,
        on_time_s=duty * period,
        off_time_s=(1.0 - duty) * period,
        ideal_output_voltage_v=vout,
        ideal_output_current_a=iout,
        inductor_ripple_app=ripple_i,
        inductor_peak_current_a=peak,
        inductor_valley_current_a=valley,
        capacitor_ripple_vpp=ripple_v,
        boundary_current_a=boundary_i,
        boundary_resistance_ohm=(vout / boundary_i),
        ccm_assumption_valid=valley > 0.0,
    )


def calculate_ideal_dcm(config: BuckConfig) -> DcmTheoryResult:
    """计算理想 DCM 变换比。

    ``K = 2L / (R*T)``，``M = 2 / (1 + sqrt(1 + 4K/D^2))``。
    当 ``K >= 1 - D`` 时电路处于 CCM，该公式不适用，结果标记为不可用。
    """
    if not isinstance(config, BuckConfig):
        raise ValueError("config must be BuckConfig")
    k = 2.0 * config.inductance_h / (config.load_resistance_ohm * config.period_s)
    boundary_k = 1.0 - config.duty_cycle
    ratio = 2.0 / (1.0 + math.sqrt(1.0 + 4.0 * k / config.duty_cycle**2))
    return DcmTheoryResult(
        k=k,
        conversion_ratio=ratio,
        output_voltage_v=ratio * config.input_voltage_v,
        dcm_assumption_valid=k < boundary_k,
        boundary_k=boundary_k,
    )


def duty_cycle_for_output(input_voltage_v: float, output_voltage_v: float) -> float:
    """由理想 CCM 关系反推占空比 ``D = Vout / Vin``。"""
    vin = positive_number(input_voltage_v, "input_voltage_v")
    vout = positive_number(output_voltage_v, "output_voltage_v")
    if vout >= vin:
        raise ValueError("output_voltage_v must be lower than input_voltage_v")
    return vout / vin


def inductor_for_ripple(
    input_voltage_v: float,
    output_voltage_v: float,
    duty_cycle: float,
    switching_frequency_hz: float,
    ripple_current_app: float,
) -> float:
    """按允许电感电流纹波反推所需电感 ``L``（H）。"""
    vin = positive_number(input_voltage_v, "input_voltage_v")
    vout = positive_number(output_voltage_v, "output_voltage_v")
    duty = finite_number(duty_cycle, "duty_cycle")
    frequency = positive_number(switching_frequency_hz, "switching_frequency_hz")
    ripple = positive_number(ripple_current_app, "ripple_current_app")
    if not 0 < duty < 1:
        raise ValueError("duty_cycle must be in (0, 1)")
    if vout >= vin:
        raise ValueError("output_voltage_v must be lower than input_voltage_v")
    return (vin - vout) * duty / (frequency * ripple)


def capacitance_for_ripple(
    ripple_current_app: float,
    switching_frequency_hz: float,
    ripple_voltage_vpp: float,
) -> float:
    """按允许输出纹波反推理想最小电容 ``C``（F）。

    不包含 ESR、ESL、负载瞬态与控制稳定性要求。
    """
    ripple_i = positive_number(ripple_current_app, "ripple_current_app")
    frequency = positive_number(switching_frequency_hz, "switching_frequency_hz")
    ripple_v = positive_number(ripple_voltage_vpp, "ripple_voltage_vpp")
    return ripple_i / (8.0 * frequency * ripple_v)


def boundary_load_resistance(config: BuckConfig) -> float:
    """理想 CCM/DCM 临界负载电阻（Ω）。"""
    return calculate_ideal_buck(config).boundary_resistance_ohm

"""工程误差预算（Task 27）。

分别输出单项误差、最坏情况线性叠加、独立随机误差假设下的 RSS 估计。
RSS 仅作为统计估计，不是有保证的最坏情况精度；也不能重复计入已包含在
芯片总精度规格中的子项。
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Sequence

from sensing.adc import ADCConfig
from sensing.voltage_decoder import four_resistor_output


class ErrorBudgetError(ValueError):
    """误差预算输入非法。"""


@dataclass(frozen=True)
class BudgetItem:
    name: str
    value: float
    unit: str
    evidence: str
    formula: str

    def as_dict(self) -> dict[str, float | str]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "evidence": self.evidence,
            "formula": self.formula,
        }


def summarize_budget(items: Sequence[BudgetItem], unit: str) -> dict[str, object]:
    values = [abs(item.value) for item in items]
    worst_case = float(sum(values))
    rss = float(math.sqrt(sum(value * value for value in values)))
    dominant = max(items, key=lambda item: abs(item.value)) if items else None
    return {
        "unit": unit,
        "items": [item.as_dict() for item in items],
        "worst_case_linear_sum": worst_case,
        "rss_estimate": rss,
        "dominant_item": dominant.name if dominant else "",
        "dominant_value": abs(dominant.value) if dominant else 0.0,
        "note": "最坏情况为线性叠加；RSS 为独立随机假设下的统计估计，不是保证值。",
    }


def resistor_mismatch_worst_case_error(
    *,
    r1_ohm: float,
    r2_ohm: float,
    r3_ohm: float,
    r4_ohm: float,
    reference_v: float,
    tolerance_percent: float,
    common_mode_v: float,
    differential_v: float,
) -> float:
    """枚举四个电阻 ±容差的 16 个角点，返回折算到输入端的最大电压误差。"""
    fraction = tolerance_percent / 100.0
    vhigh = common_mode_v + 0.5 * differential_v
    vlow = common_mode_v - 0.5 * differential_v
    ideal = four_resistor_output(
        vhigh, vlow, r1_ohm=r1_ohm, r2_ohm=r2_ohm, r3_ohm=r3_ohm, r4_ohm=r4_ohm, reference_v=reference_v
    )
    gain = r2_ohm / r1_ohm
    worst = 0.0
    for signs in itertools.product((-1.0, 1.0), repeat=4):
        actual = four_resistor_output(
            vhigh,
            vlow,
            r1_ohm=r1_ohm * (1.0 + signs[0] * fraction),
            r2_ohm=r2_ohm * (1.0 + signs[1] * fraction),
            r3_ohm=r3_ohm * (1.0 + signs[2] * fraction),
            r4_ohm=r4_ohm * (1.0 + signs[3] * fraction),
            reference_v=reference_v,
        )
        worst = max(worst, abs(actual - ideal) / gain)
    return worst


def voltage_error_budget(
    *,
    r1_ohm: float,
    r2_ohm: float,
    r3_ohm: float,
    r4_ohm: float,
    reference_v: float,
    adc_config: ADCConfig,
    cell_voltage_v: float,
    common_mode_v: float,
    resistor_tolerance_percent: float,
    opamp_offset_v: float,
    adc_offset_v: float,
    adc_gain_error_fraction: float,
    adc_noise_v: float,
    reference_tolerance_percent: float,
    opamp_cmrr_db: float = 100.0,
    input_bias_current_a: float = 0.0,
    input_network_ohm: float = 50_000.0,
    temperature_drift_v: float = 0.0,
) -> dict[str, object]:
    gain = r2_ohm / r1_ohm
    items = [
        BudgetItem(
            "四电阻失配（含增益与共模）",
            resistor_mismatch_worst_case_error(
                r1_ohm=r1_ohm,
                r2_ohm=r2_ohm,
                r3_ohm=r3_ohm,
                r4_ohm=r4_ohm,
                reference_v=reference_v,
                tolerance_percent=resistor_tolerance_percent,
                common_mode_v=common_mode_v,
                differential_v=cell_voltage_v,
            ),
            "V",
            "teaching_assumption",
            "16 个 ±容差角点中的最大输入折算误差",
        ),
        BudgetItem(
            "运放输入失调（噪声增益 1+k）",
            opamp_offset_v * (1.0 + gain) / gain,
            "V",
            "teaching_assumption",
            "Vos*(1+R2/R1)/(R2/R1)",
        ),
        BudgetItem(
            "输入偏置电流",
            input_bias_current_a * input_network_ohm,
            "V",
            "teaching_assumption",
            "Ib*Rin",
        ),
        BudgetItem(
            "运放有限 CMRR",
            common_mode_v / (10.0 ** (opamp_cmrr_db / 20.0)),
            "V",
            "teaching_assumption",
            "Vcm/10^(CMRR/20)",
        ),
        BudgetItem(
            "差分参考电压误差",
            reference_v * reference_tolerance_percent / 100.0 / gain,
            "V",
            "teaching_assumption",
            "ΔVref/k",
        ),
        BudgetItem(
            "ADC 量化",
            adc_config.lsb_v / gain,
            "V",
            "adc_behavioral_model",
            "LSB/k",
        ),
        BudgetItem(
            "ADC 增益误差",
            adc_gain_error_fraction * (reference_v + gain * cell_voltage_v) / gain,
            "V",
            "teaching_assumption",
            "εG*Vout/k",
        ),
        BudgetItem(
            "ADC 失调",
            adc_offset_v / gain,
            "V",
            "teaching_assumption",
            "Vos_adc/k",
        ),
        BudgetItem(
            "ADC 输入噪声",
            adc_noise_v / gain,
            "V",
            "adc_behavioral_model",
            "Vn/k",
        ),
        BudgetItem(
            "温度漂移",
            temperature_drift_v,
            "V",
            "teaching_assumption",
            "未单独建模的温漂预留项",
        ),
    ]
    return summarize_budget(items, "V")


def current_error_budget(
    *,
    shunt_ohm: float,
    amplifier_gain: float,
    reference_v: float,
    adc_config: ADCConfig,
    current_a: float,
    shunt_tolerance_percent: float,
    shunt_tcr_ppm_per_c: float,
    temperature_delta_c: float,
    input_offset_v: float,
    gain_error_fraction: float,
    zero_reference_error_v: float,
    adc_offset_v: float,
    adc_gain_error_fraction: float,
    adc_noise_v: float,
    reference_tolerance_percent: float,
) -> dict[str, object]:
    transconductance = amplifier_gain * shunt_ohm
    output_v = reference_v + amplifier_gain * shunt_ohm * current_a
    items = [
        BudgetItem(
            "分流电阻容差",
            current_a * shunt_tolerance_percent / 100.0,
            "A",
            "teaching_assumption",
            "I*Δtol",
        ),
        BudgetItem(
            "分流电阻温漂",
            current_a * shunt_tcr_ppm_per_c * 1e-6 * temperature_delta_c,
            "A",
            "teaching_assumption",
            "I*TCR*ΔT",
        ),
        BudgetItem(
            "放大器输入失调",
            input_offset_v / shunt_ohm,
            "A",
            "datasheet_max",
            "Vos/Rshunt",
        ),
        BudgetItem(
            "放大器增益误差",
            current_a * gain_error_fraction,
            "A",
            "datasheet_max",
            "I*εG",
        ),
        BudgetItem(
            "零点参考偏差",
            zero_reference_error_v / transconductance,
            "A",
            "teaching_assumption",
            "ΔVref/(G*Rshunt)",
        ),
        BudgetItem(
            "ADC 参考偏差",
            reference_tolerance_percent / 100.0 * current_a,
            "A",
            "teaching_assumption",
            "εRef*I（近似）",
        ),
        BudgetItem(
            "ADC 量化",
            adc_config.lsb_v / transconductance,
            "A",
            "adc_behavioral_model",
            "LSB/(G*Rshunt)",
        ),
        BudgetItem(
            "ADC 增益误差",
            adc_gain_error_fraction * output_v / transconductance,
            "A",
            "teaching_assumption",
            "εG_adc*Vout/(G*Rshunt)",
        ),
        BudgetItem(
            "ADC 失调",
            adc_offset_v / transconductance,
            "A",
            "teaching_assumption",
            "Vos_adc/(G*Rshunt)",
        ),
        BudgetItem(
            "ADC 输入噪声",
            adc_noise_v / transconductance,
            "A",
            "adc_behavioral_model",
            "Vn/(G*Rshunt)",
        ),
    ]
    return summarize_budget(items, "A")


def temperature_error_budget(
    *,
    r25_ohm: float,
    beta_k: float,
    pullup_ohm: float,
    excitation_v: float,
    temperature_c: float,
    adc_config: ADCConfig,
    r25_tolerance_percent: float,
    beta_tolerance_percent: float,
    pullup_tolerance_percent: float,
) -> dict[str, object]:
    from sensing.temperature_decoder import ntc_resistance, ntc_temperature, voltage_sensitivity_v_per_c

    def delta_temperature(resistance: float, beta: float, pullup: float) -> float:
        voltage = excitation_v * resistance / (pullup + resistance)
        recovered_resistance = pullup * voltage / (excitation_v - voltage)
        recovered = ntc_temperature(recovered_resistance, r25_ohm=r25_ohm, beta_k=beta)
        return recovered

    base_resistance = ntc_resistance(temperature_c, r25_ohm=r25_ohm, beta_k=beta_k)
    base = delta_temperature(base_resistance, beta_k, pullup_ohm)
    r25_delta = delta_temperature(
        base_resistance * (1.0 + r25_tolerance_percent / 100.0), beta_k, pullup_ohm
    ) - base
    beta_delta = delta_temperature(
        base_resistance, beta_k * (1.0 + beta_tolerance_percent / 100.0), pullup_ohm
    ) - base
    pullup_delta = delta_temperature(
        base_resistance, beta_k, pullup_ohm * (1.0 + pullup_tolerance_percent / 100.0)
    ) - base
    sensitivity = abs(voltage_sensitivity_v_per_c(temperature_c, r25_ohm=r25_ohm, beta_k=beta_k, pullup_ohm=pullup_ohm, excitation_v=excitation_v))
    quantization = adc_config.lsb_v / sensitivity if sensitivity > 0.0 else float("nan")
    items = [
        BudgetItem("NTC R25 容差", r25_delta, "degC", "teaching_assumption", "∂T/∂R25*ΔR25"),
        BudgetItem("NTC B 值容差", beta_delta, "degC", "teaching_assumption", "∂T/∂B*ΔB"),
        BudgetItem("上拉电阻容差", pullup_delta, "degC", "teaching_assumption", "∂T/∂Rpull*ΔRpull"),
        BudgetItem("ADC 量化", quantization, "degC", "adc_behavioral_model", "LSB/(|dV/dT|)"),
        BudgetItem("参考电压（比率式）", 0.0, "degC", "analytical_theory", "共源参考误差理想抵消"),
        BudgetItem("NTC 自热", float("nan"), "degC", "NOT_VERIFIED", "缺少真实耗散系数，未计入"),
    ]
    finite_items = [item for item in items if math.isfinite(item.value)]
    summary = summarize_budget(finite_items, "degC")
    summary["unverified_items"] = [item.as_dict() for item in items if not math.isfinite(item.value)]
    return summary

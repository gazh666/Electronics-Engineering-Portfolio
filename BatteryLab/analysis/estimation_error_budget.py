"""SOC 估计误差预算（Task 9 / Task 19 / Task 21）。

核心关系：

1. OCV 反演：``ΔSOC ≈ ΔV / (dOCV/dSOC)``。
2. 电流固定失调：``ΔSOC(t) = -I_offset · t / (3600 · Q)``。
3. 容量偏差：真实容量 ``Q_true``、估计器假定 ``Q_est`` 时，放掉 ``Δq`` Ah 后
   真实 SOC 变化 ``Δq/Q_true``，估计 SOC 变化 ``Δq/Q_est``，二者之差即误差。

全部输出以百分点 pp 表示。这些是教学误差预算，不是量产 BMS 的实测精度。
"""

from __future__ import annotations

import math


class ErrorBudgetError(ValueError):
    """误差预算输入非法。"""


def voltage_error_to_soc_error_pp(
    voltage_error_v: float,
    ocv_slope_v_per_soc: float,
) -> float:
    """电压误差按局部 OCV 斜率折算为 SOC 误差（pp）。"""
    if not all(math.isfinite(float(value)) for value in (voltage_error_v, ocv_slope_v_per_soc)):
        raise ErrorBudgetError("Invalid data")
    if float(ocv_slope_v_per_soc) <= 0.0:
        raise ErrorBudgetError("Invalid OCV slope")
    return float(voltage_error_v) / float(ocv_slope_v_per_soc) * 100.0


def calculate_offset_drift_pp(
    offset_a: float,
    duration_s: float,
    capacity_ah: float,
) -> float:
    """固定电流失调在持续积分后的 SOC 漂移（pp）。"""
    if not all(math.isfinite(float(value)) for value in (offset_a, duration_s, capacity_ah)):
        raise ErrorBudgetError("Invalid parameter")
    if float(capacity_ah) <= 0.0 or float(duration_s) < 0.0:
        raise ErrorBudgetError("Invalid capacity or time")
    return -float(offset_a) * float(duration_s) / (3600.0 * float(capacity_ah)) * 100.0


def capacity_mismatch_soc_error_pp(
    charge_throughput_ah: float,
    true_capacity_ah: float,
    assumed_capacity_ah: float,
) -> float:
    """放/充电量相同时，容量假定偏差造成的 SOC 误差（pp）。"""
    if not all(
        math.isfinite(float(value))
        for value in (charge_throughput_ah, true_capacity_ah, assumed_capacity_ah)
    ):
        raise ErrorBudgetError("Invalid parameter")
    if float(true_capacity_ah) <= 0.0 or float(assumed_capacity_ah) <= 0.0:
        raise ErrorBudgetError("Invalid capacity")
    true_delta = float(charge_throughput_ah) / float(true_capacity_ah)
    assumed_delta = float(charge_throughput_ah) / float(assumed_capacity_ah)
    return (assumed_delta - true_delta) * 100.0


def resistance_mismatch_voltage_error_v(
    current_a: float,
    true_r0_ohm: float,
    assumed_r0_ohm: float,
) -> float:
    """R0 偏差造成的端电压预测误差（V），仅计欧姆项。"""
    if not all(
        math.isfinite(float(value)) for value in (current_a, true_r0_ohm, assumed_r0_ohm)
    ):
        raise ErrorBudgetError("Invalid parameter")
    return float(current_a) * (float(assumed_r0_ohm) - float(true_r0_ohm))


def adc_voltage_error_to_soc_pp(
    adc_resolution_bits: int,
    reference_voltage_v: float,
    ocv_slope_v_per_soc: float,
    *,
    analog_gain: float = 1.0,
) -> dict[str, float]:
    """ADC 量化步距折算到 SOC 误差（pp）。"""
    if adc_resolution_bits <= 0:
        raise ErrorBudgetError("Invalid ADC resolution")
    if not math.isfinite(float(reference_voltage_v)) or float(reference_voltage_v) <= 0.0:
        raise ErrorBudgetError("Invalid ADC reference")
    if not math.isfinite(float(analog_gain)) or float(analog_gain) == 0.0:
        raise ErrorBudgetError("Invalid analog gain")
    lsb_v = float(reference_voltage_v) / (2**int(adc_resolution_bits))
    input_referred_v = lsb_v / abs(float(analog_gain))
    return {
        "lsb_v": float(lsb_v),
        "input_referred_lsb_v": float(input_referred_v),
        "soc_error_pp": voltage_error_to_soc_error_pp(input_referred_v, ocv_slope_v_per_soc),
    }


def build_error_budget_table(ocv_slope_v_per_soc: float = 0.5) -> list[dict[str, float | str]]:
    """教学用电压误差 → SOC 误差预算表。"""
    rows: list[dict[str, float | str]] = []
    for voltage_error in (0.001, 0.005, 0.010, 0.020, 0.050):
        for slope in (0.5, 0.2, 0.1):
            rows.append(
                {
                    "voltage_error_mv": float(voltage_error * 1000.0),
                    "ocv_slope_v_per_soc": float(slope),
                    "soc_error_pp": voltage_error_to_soc_error_pp(voltage_error, slope),
                    "note": "参考斜率 %.2f V/SOC" % slope,
                }
            )
    return rows


def offset_drift_table(capacity_ah: float = 2.0) -> list[dict[str, float]]:
    """教学用电流失调 → 时间 → SOC 漂移表。"""
    rows: list[dict[str, float]] = []
    for offset_ma in (-20.0, -10.0, -5.0, 5.0, 10.0, 20.0):
        for hours in (1.0, 5.0, 10.0, 24.0):
            rows.append(
                {
                    "offset_ma": float(offset_ma),
                    "duration_h": float(hours),
                    "capacity_ah": float(capacity_ah),
                    "drift_pp": calculate_offset_drift_pp(
                        offset_ma / 1000.0, hours * 3600.0, capacity_ah
                    ),
                }
            )
    return rows

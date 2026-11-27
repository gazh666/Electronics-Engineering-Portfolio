"""基于线性化平均模型的环路稳定性分析。

重要限制：这里分析的是平均模型的环路增益 L(s)=PI(s)·Gpwm·Gp(s)，
不是开关级 SPICE 的完整闭环 AC 分析；不能据此宣称开关电路大信号稳定。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from circuits.validators import positive_number
from control.averaged_buck import AveragedBuckParameters, operating_point
from control.loop_analysis import (
    analyze_loop,
    bandwidth_hz,
    classify_poles,
    closed_loop_poles,
    loop_gain,
)
from control.pwm_modulator import sine_carrier_gain, threshold_from_effective_duty
from control.transfer_functions import (
    TransferFunction,
    frequency_grid,
    nonideal_buck_control_to_output,
)


def solve_operating_duty(
    parameters: AveragedBuckParameters,
    target_v: float,
    *,
    nonideal: bool = True,
    tolerance: float = 1e-10,
) -> float:
    """在给定负载下二分求满足目标输出电压的稳态占空比。"""
    target = positive_number(target_v, "target_v")
    low, high = 0.0, 0.95
    v_low = operating_point(low, parameters, nonideal=nonideal).output_voltage_v - target
    v_high = operating_point(high, parameters, nonideal=nonideal).output_voltage_v - target
    if v_low > 0 or v_high < 0:
        raise ValueError("target voltage is outside the achievable range of the average model")
    for _ in range(200):
        middle = 0.5 * (low + high)
        value = operating_point(middle, parameters, nonideal=nonideal).output_voltage_v - target
        if abs(value) < tolerance or (high - low) < tolerance:
            return middle
        if value > 0:
            high = middle
        else:
            low = middle
    return 0.5 * (low + high)


def carrier_small_signal_gain(effective_duty: float) -> float:
    """正弦载波在给定平均占空比处的小信号增益 dD/dd。"""
    threshold = threshold_from_effective_duty(effective_duty)
    return sine_carrier_gain(threshold)


def stability_report(
    parameters: AveragedBuckParameters,
    kp: float,
    ki: float,
    *,
    target_v: float,
    pwm_gain: float | None = None,
    frequencies_hz: np.ndarray | None = None,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成平均模型稳定性报告（裕度、穿越、极点、带宽）。"""
    if not isinstance(parameters, AveragedBuckParameters):
        raise ValueError("parameters must be AveragedBuckParameters")
    duty = solve_operating_duty(parameters, target_v)
    plant, linearization = nonideal_buck_control_to_output(parameters, duty)
    modulator = (
        carrier_small_signal_gain(duty) if pwm_gain is None else positive_number(pwm_gain, "pwm_gain")
    )
    frequencies = (
        frequency_grid(1.0, 1e6, 60)
        if frequencies_hz is None
        else np.asarray(frequencies_hz, dtype=float)
    )
    response = loop_gain(frequencies, plant, kp, ki, pwm_gain=modulator)
    margins = analyze_loop(frequencies, response)
    poles = classify_poles(closed_loop_poles(plant, kp, ki, pwm_gain=modulator))
    bandwidth = bandwidth_hz(plant, kp, ki, pwm_gain=modulator)
    magnitude_db = 20.0 * np.log10(np.maximum(np.abs(response), 1e-30))
    phase_deg = np.degrees(np.unwrap(np.angle(response)))

    report: dict[str, Any] = {
        "analysis_type": "linearized_average_model",
        "model_source": "averaged_model",
        "not_full_spice_ac_analysis": True,
        "operating_duty": duty,
        "target_v": target_v,
        "kp": float(kp),
        "ki": float(ki),
        "pwm_gain": float(modulator),
        "phase_margin_deg": margins["phase_margin_deg"],
        "gain_margin_db": margins["gain_margin_db"],
        "status": margins["status"],
        "messages": list(margins["messages"]),
        "magnitude_crossings": margins["magnitude_crossings"],
        "gain_margin_crossings": margins["gain_margin_crossings"],
        "closed_loop_poles": poles,
        "bandwidth_hz": bandwidth,
        "plant": plant.to_dict(),
        "linearization": linearization,
        "minimum_magnitude_db": margins["minimum_magnitude_db"],
    }
    if limits:
        report["limit_check"] = judge_stability_limits(report, limits)
    report["frequency_response"] = pd.DataFrame(
        {
            "frequency_hz": frequencies,
            "magnitude_db": magnitude_db,
            "phase_deg": phase_deg,
        }
    )
    return report


def judge_stability_limits(
    report: dict[str, Any], limits: dict[str, Any]
) -> dict[str, Any]:
    """按 transient_limits 判定；没有增益裕度穿越时记为 NOT_RESOLVED 而非通过。"""
    checks: list[dict[str, Any]] = []
    pm_limit = limits.get("phase_margin_deg", {}).get("min")
    gm_limit = limits.get("finite_gain_margin_db", {}).get("min")
    phase_margin = report.get("phase_margin_deg")
    gain_margin = report.get("gain_margin_db")
    if pm_limit is not None:
        if phase_margin is None or not math.isfinite(float(phase_margin)):
            checks.append(
                {
                    "name": "phase_margin_deg",
                    "limit": pm_limit,
                    "value": None,
                    "status": "NOT_RESOLVED",
                }
            )
        else:
            checks.append(
                {
                    "name": "phase_margin_deg",
                    "limit": pm_limit,
                    "value": float(phase_margin),
                    "status": "PASS" if float(phase_margin) >= float(pm_limit) else "FAIL",
                }
            )
    if gm_limit is not None:
        if gain_margin is None or not math.isfinite(float(gain_margin)):
            checks.append(
                {
                    "name": "finite_gain_margin_db",
                    "limit": gm_limit,
                    "value": None,
                    "status": "NOT_RESOLVED",
                }
            )
        else:
            checks.append(
                {
                    "name": "finite_gain_margin_db",
                    "limit": gm_limit,
                    "value": float(gain_margin),
                    "status": "PASS" if float(gain_margin) >= float(gm_limit) else "FAIL",
                }
            )
    failed = [item for item in checks if item["status"] == "FAIL"]
    unresolved = [item for item in checks if item["status"] == "NOT_RESOLVED"]
    return {
        "checks": checks,
        "status": "FAIL" if failed else ("NOT_RESOLVED" if unresolved else "PASS"),
    }


def plant_from_parameters(
    parameters: AveragedBuckParameters, duty: float
) -> tuple[TransferFunction, dict[str, Any]]:
    return nonideal_buck_control_to_output(parameters, duty)


def describe_closed_loop_poles(report: dict[str, Any]) -> pd.DataFrame:
    poles = report.get("closed_loop_poles", {}).get("poles", [])
    rows = []
    for index, (real, imag) in enumerate(poles):
        magnitude = math.hypot(real, imag)
        rows.append(
            {
                "pole_index": index,
                "real": real,
                "imag": imag,
                "natural_frequency_hz": magnitude / (2.0 * math.pi),
                "damping_ratio": -real / magnitude if magnitude > 1e-15 else 0.0,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "carrier_small_signal_gain",
    "describe_closed_loop_poles",
    "judge_stability_limits",
    "plant_from_parameters",
    "solve_operating_duty",
    "stability_report",
]

"""RC 滤波理论与 SPICE 对照（Task 11/12）。"""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np


class FilterAnalysisError(ValueError):
    """滤波分析输入非法。"""


def first_order_magnitude(frequency_hz: np.ndarray, cutoff_hz: float) -> np.ndarray:
    if cutoff_hz <= 0.0:
        raise FilterAnalysisError("截止频率必须为正")
    ratio = np.asarray(frequency_hz, dtype=float) / cutoff_hz
    return 1.0 / np.sqrt(1.0 + ratio**2)


def first_order_phase_deg(frequency_hz: np.ndarray, cutoff_hz: float) -> np.ndarray:
    ratio = np.asarray(frequency_hz, dtype=float) / cutoff_hz
    return -np.degrees(np.arctan(ratio))


def theoretical_attenuation_db(frequency_hz: float, cutoff_hz: float) -> float:
    if frequency_hz <= 0.0 or cutoff_hz <= 0.0:
        raise FilterAnalysisError("频率必须为正")
    ratio = frequency_hz / cutoff_hz
    return -10.0 * math.log10(1.0 + ratio**2)


def step_response(time_s: np.ndarray, tau_s: float, step_v: float) -> np.ndarray:
    if tau_s <= 0.0:
        raise FilterAnalysisError("时间常数必须为正")
    return step_v * (1.0 - np.exp(-np.asarray(time_s, dtype=float) / tau_s))


def extract_ac_metrics(
    frequency_hz: np.ndarray,
    gain_db: np.ndarray,
    phase_deg: np.ndarray,
    *,
    cutoff_hz: float,
) -> dict[str, float]:
    low_frequency_gain_db = float(gain_db[0])
    target = low_frequency_gain_db - 3.0
    actual_cutoff = float("nan")
    for index in range(1, len(gain_db)):
        if gain_db[index] <= target <= gain_db[index - 1]:
            f0, f1 = frequency_hz[index - 1], frequency_hz[index]
            g0, g1 = gain_db[index - 1], gain_db[index]
            actual_cutoff = float(10.0 ** (math.log10(f0) + (target - g0) / (g1 - g0) * (math.log10(f1) - math.log10(f0))))
            break
    metrics = {
        "low_frequency_gain_db": low_frequency_gain_db,
        "spice_cutoff_hz": actual_cutoff,
        "theoretical_cutoff_hz": float(cutoff_hz),
        "cutoff_relative_error": (actual_cutoff - cutoff_hz) / cutoff_hz if math.isfinite(actual_cutoff) else float("nan"),
        "phase_at_cutoff_deg": float(np.interp(math.log10(cutoff_hz), np.log10(frequency_hz), phase_deg)),
    }
    for frequency in (1e3, 1e4, 1e5, 1e6):
        key = f"attenuation_{int(frequency)}hz_db"
        metrics[key] = float(np.interp(math.log10(frequency), np.log10(frequency_hz), gain_db))
        metrics[key + "_theoretical"] = theoretical_attenuation_db(frequency, cutoff_hz)
    return metrics


def compare_step_metrics(measured: Mapping[str, float], tau_s: float) -> dict[str, float]:
    theoretical_rise = 2.197 * tau_s
    theoretical_settling = 4.605 * tau_s
    return {
        "measured_rise_time_s": float(measured["rise_time_10_90_s"]),
        "theoretical_rise_time_s": float(theoretical_rise),
        "rise_time_relative_error": float((measured["rise_time_10_90_s"] - theoretical_rise) / theoretical_rise),
        "measured_settling_time_s": float(measured["settling_time_1pct_s"]),
        "theoretical_settling_time_s": float(theoretical_settling),
        "overshoot_percent": float(measured["overshoot_percent"]),
        "steady_state_error_v": float(measured["steady_state_error_v"]),
    }

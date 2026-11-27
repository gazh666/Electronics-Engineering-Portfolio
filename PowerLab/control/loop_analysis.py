"""环路频响分析：0 dB 穿越、相位裕度、增益裕度、闭环极点与带宽。

只描述线性化平均模型上的环路增益，不是完整闭环大信号稳定性证明。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from circuits.validators import finite_number, positive_number

from .transfer_functions import TransferFunction


@dataclass(frozen=True)
class MarginCrossing:
    frequency_hz: float
    magnitude_db: float
    phase_deg: float
    phase_margin_deg: float


@dataclass(frozen=True)
class GainMarginCrossing:
    frequency_hz: float
    magnitude_db: float
    phase_deg: float
    gain_margin_db: float


def pi_response(kp: float, ki: float, frequencies_hz: np.ndarray) -> np.ndarray:
    """PI 频响 Kp + Ki/(jω)。"""
    gain_p = finite_number(kp, "kp")
    gain_i = finite_number(ki, "ki")
    if gain_p < 0 or gain_i < 0:
        raise ValueError("PI gains must be nonnegative")
    omega = 2.0 * np.pi * np.asarray(frequencies_hz, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return gain_p + gain_i / (1j * omega)


def loop_gain(
    frequencies_hz: np.ndarray,
    plant: TransferFunction,
    kp: float,
    ki: float,
    *,
    pwm_gain: float = 1.0,
    sensor_gain: float = 1.0,
) -> np.ndarray:
    """L(s) = Gc(s)·Gpwm·Gp(s)·H(s)。"""
    modulator = positive_number(pwm_gain, "pwm_gain")
    sensor = positive_number(sensor_gain, "sensor_gain")
    return pi_response(kp, ki, frequencies_hz) * modulator * sensor * plant.frequency_response(frequencies_hz)


def _fraction(values: np.ndarray, index: int, target: float = 0.0) -> float:
    y0 = values[index] - target
    y1 = values[index + 1] - target
    if y1 == y0:
        return 0.0
    value = -y0 / (y1 - y0)
    return min(1.0, max(0.0, value))


def _log_interpolate(frequencies: np.ndarray, index: int, fraction: float) -> float:
    x0, x1 = frequencies[index], frequencies[index + 1]
    if x0 > 0 and x1 > 0:
        return float(x0 * (x1 / x0) ** fraction)
    return float(x0 + fraction * (x1 - x0))


def _linear_interpolate(values: np.ndarray, index: int, fraction: float) -> float:
    return float(values[index] + fraction * (values[index + 1] - values[index]))


def analyze_loop(
    frequencies_hz: Iterable[float],
    response: np.ndarray,
    *,
    magnitude_tolerance_db: float = 1e-9,
    phase_tolerance_deg: float = 1e-9,
) -> dict[str, Any]:
    """分析环路增益，返回穿越点、裕度与状态。

    状态：``STABLE`` / ``LOW_MARGIN`` / ``UNSTABLE`` / ``NO_CROSSOVER``。
    没有 0 dB 穿越时返回 ``NO_CROSSOVER``，不伪造相位裕度。
    """
    frequencies = np.asarray(list(frequencies_hz), dtype=float)
    values = np.asarray(response, dtype=complex)
    if frequencies.size != values.size or frequencies.size < 3:
        raise ValueError("frequencies and response must be equally sized (>= 3)")
    magnitude_db = 20.0 * np.log10(np.maximum(np.abs(values), 1e-30))
    phase_deg = np.degrees(np.unwrap(np.angle(values)))

    crossings: list[MarginCrossing] = []
    for index in range(frequencies.size - 1):
        a = magnitude_db[index] - magnitude_tolerance_db
        b = magnitude_db[index + 1] - magnitude_tolerance_db
        if (a > 0 >= b) or (a < 0 <= b):
            fraction = _fraction(magnitude_db, index, magnitude_tolerance_db)
            frequency = _log_interpolate(frequencies, index, fraction)
            magnitude = _linear_interpolate(magnitude_db, index, fraction)
            phase = _linear_interpolate(phase_deg, index, fraction)
            phase_margin = 180.0 + phase
            crossings.append(
                MarginCrossing(
                    frequency_hz=frequency,
                    magnitude_db=magnitude,
                    phase_deg=phase,
                    phase_margin_deg=phase_margin,
                )
            )

    gain_crossings: list[GainMarginCrossing] = []
    shifted = phase_deg + 180.0
    for index in range(frequencies.size - 1):
        a = shifted[index] - phase_tolerance_deg
        b = shifted[index + 1] - phase_tolerance_deg
        # 相位下降穿过 −180°−360k 时产生增益裕度。
        if a >= 0 > b:
            fraction = _fraction(shifted, index, phase_tolerance_deg)
            frequency = _log_interpolate(frequencies, index, fraction)
            magnitude = _linear_interpolate(magnitude_db, index, fraction)
            gain_crossings.append(
                GainMarginCrossing(
                    frequency_hz=frequency,
                    magnitude_db=magnitude,
                    phase_deg=-180.0,
                    gain_margin_db=-magnitude,
                )
            )

    messages: list[str] = []
    if not crossings:
        status = "NO_CROSSOVER"
        messages.append("loop gain never crosses 0 dB; phase margin not resolved")
        minimum_margin = math.nan
    else:
        minimum_margin = min(c.phase_margin_deg for c in crossings)
        if minimum_margin < 0:
            status = "UNSTABLE"
            messages.append(f"negative phase margin {minimum_margin:.2f} deg")
        elif minimum_margin < 30.0:
            status = "LOW_MARGIN"
            messages.append(f"low phase margin {minimum_margin:.2f} deg")
        else:
            status = "STABLE"
        if len(crossings) > 1:
            messages.append(f"{len(crossings)} 0 dB crossings detected")
        for margin in gain_crossings:
            if margin.gain_margin_db < 6.0:
                messages.append(
                    f"gain margin {margin.gain_margin_db:.2f} dB below 6 dB at "
                    f"{margin.frequency_hz:.1f} Hz"
                )
                if status == "STABLE":
                    status = "LOW_MARGIN"

    return {
        "status": status,
        "magnitude_crossings": [c.__dict__ for c in crossings],
        "gain_margin_crossings": [g.__dict__ for g in gain_crossings],
        "phase_margin_deg": minimum_margin,
        "gain_margin_db": (
            min(g.gain_margin_db for g in gain_crossings)
            if gain_crossings
            else math.nan
        ),
        "minimum_magnitude_db": float(np.min(magnitude_db)),
        "messages": messages,
        "analysis_type": "linearized_average_model",
    }


def closed_loop_characteristic(
    plant: TransferFunction,
    kp: float,
    ki: float,
    *,
    pwm_gain: float = 1.0,
) -> np.ndarray:
    """返回闭环特征多项式：s·den + (Kp s + Ki)·Gpwm·num。"""
    modulator = positive_number(pwm_gain, "pwm_gain")
    gain_p = finite_number(kp, "kp")
    gain_i = finite_number(ki, "ki")
    numerator = plant.num * modulator
    s_den = np.concatenate((plant.den, np.zeros(1)))
    pi_num = np.polymul(np.array([gain_p, gain_i]), numerator)
    n = max(s_den.size, pi_num.size)
    denominator = np.concatenate((np.zeros(n - s_den.size), s_den))
    pi_part = np.concatenate((np.zeros(n - pi_num.size), pi_num))
    return denominator + pi_part


def closed_loop_poles(
    plant: TransferFunction, kp: float, ki: float, *, pwm_gain: float = 1.0
) -> np.ndarray:
    return np.roots(closed_loop_characteristic(plant, kp, ki, pwm_gain=pwm_gain))


def classify_poles(poles: np.ndarray, *, stability_margin: float = 0.0) -> dict[str, Any]:
    """按实部判定稳定/临界/不稳定，并给出最小衰减率。"""
    values = np.asarray(poles, dtype=complex)
    if values.size == 0:
        return {"status": "NOT_RESOLVED", "magnitude": 0.0, "poles": [], "messages": ["no poles"]}
    real = np.real(values)
    maximum = float(np.max(real))
    if maximum > stability_margin:
        status = "UNSTABLE"
    elif maximum >= -stability_margin:
        status = "MARGINAL"
    else:
        status = "STABLE"
    return {
        "status": status,
        "maximum_real_part": maximum,
        "minimum_decay_rate": float(-maximum),
        "poles": [[float(p.real), float(p.imag)] for p in values],
        "natural_frequencies_hz": [
            float(abs(p) / (2.0 * math.pi)) for p in values
        ],
        "damping_ratios": [
            float(-p.real / abs(p)) if abs(p) > 1e-15 else 0.0 for p in values
        ],
    }


def closed_loop_transfer(
    plant: TransferFunction, kp: float, ki: float, *, pwm_gain: float = 1.0
) -> TransferFunction:
    """闭环 Vout/Vref = L/(1+L)。"""
    modulator = positive_number(pwm_gain, "pwm_gain")
    numerator = np.polymul(np.array([kp, ki]), plant.num * modulator)
    characteristic = closed_loop_characteristic(plant, kp, ki, pwm_gain=modulator)
    return TransferFunction(numerator, characteristic)


def bandwidth_hz(
    plant: TransferFunction,
    kp: float,
    ki: float,
    *,
    pwm_gain: float = 1.0,
    start_hz: float = 0.1,
    stop_hz: float = 1e6,
    points: int = 4000,
) -> float:
    """闭环 −3 dB 带宽（数值扫描）；找不到时返回 ``nan``。"""
    closed = closed_loop_transfer(plant, kp, ki, pwm_gain=pwm_gain)
    frequencies = np.logspace(math.log10(start_hz), math.log10(stop_hz), points)
    magnitude = np.abs(closed.frequency_response(frequencies))
    dc = abs(closed.evaluate(0.0))
    if dc <= 0 or not math.isfinite(dc):
        return math.nan
    target = dc / math.sqrt(2.0)
    below = np.where(magnitude <= target)[0]
    if below.size == 0:
        return math.nan
    index = int(below[0])
    if index == 0:
        return float(frequencies[0])
    # 对数插值。
    x0, x1 = frequencies[index - 1], frequencies[index]
    y0, y1 = magnitude[index - 1], magnitude[index]
    fraction = (y0 - target) / (y0 - y1) if y1 != y0 else 0.0
    return float(x0 * (x1 / x0) ** fraction)


def summarize_loop(
    frequencies_hz: np.ndarray,
    plant: TransferFunction,
    kp: float,
    ki: float,
    *,
    pwm_gain: float = 1.0,
) -> dict[str, Any]:
    """组合分析：裕度 + 极点 + 带宽。"""
    response = loop_gain(frequencies_hz, plant, kp, ki, pwm_gain=pwm_gain)
    margins = analyze_loop(frequencies_hz, response)
    poles = closed_loop_poles(plant, kp, ki, pwm_gain=pwm_gain)
    pole_summary = classify_poles(poles)
    margins["closed_loop_poles"] = pole_summary
    margins["bandwidth_hz"] = bandwidth_hz(plant, kp, ki, pwm_gain=pwm_gain)
    margins["kp"] = float(kp)
    margins["ki"] = float(ki)
    margins["pwm_gain"] = float(pwm_gain)
    return margins

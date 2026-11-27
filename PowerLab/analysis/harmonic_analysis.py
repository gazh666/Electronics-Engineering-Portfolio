"""谐波表、THD 与正弦拟合交叉验证。

谐波频率来自"实测开关频率"，而不是理论 100 kHz 常量。

对于可信频段之外的谐波、或低于噪声底的谐波，状态标记 ``NOT_RESOLVED``；
不强行给出一个看起来精确的幅值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .spectrum_analysis import SpectrumResult


@dataclass(frozen=True)
class HarmonicEntry:
    order: int
    expected_frequency_hz: float
    detected_frequency_hz: float | None
    frequency_error_hz: float | None
    amplitude_peak: float | None
    amplitude_rms: float | None
    sine_fit_amplitude: float | None
    status: str
    note: str = ""
    data_source: str = "spice_derived"

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "expected_frequency_hz": self.expected_frequency_hz,
            "detected_frequency_hz": self.detected_frequency_hz,
            "frequency_error_hz": self.frequency_error_hz,
            "amplitude_peak": self.amplitude_peak,
            "amplitude_rms": self.amplitude_rms,
            "sine_fit_amplitude": self.sine_fit_amplitude,
            "status": self.status,
            "note": self.note,
            "data_source": self.data_source,
        }


def sine_fit_amplitude(
    time_s: Any, values: Any, frequency_hz: float
) -> float:
    """在给定频率上用最小二乘拟合 ``a·sin + b·cos + c``，返回幅值。"""
    time = np.asarray(time_s, dtype=float)
    array = np.asarray(values, dtype=float)
    if time.shape != array.shape or time.size < 8:
        raise ValueError("insufficient data for sine fit")
    omega = 2.0 * np.pi * float(frequency_hz)
    design = np.column_stack(
        (np.sin(omega * time), np.cos(omega * time), np.ones_like(time))
    )
    coefficients, *_ = np.linalg.lstsq(design, array, rcond=None)
    return float(np.hypot(coefficients[0], coefficients[1]))


def analyze_harmonics(
    spectrum: SpectrumResult,
    base_frequency_hz: float,
    *,
    maximum_order: int = 10,
    tolerance_ratio: float = 0.02,
    minimum_snr: float = 3.0,
) -> list[HarmonicEntry]:
    """生成 1..maximum_order 次谐波表。"""
    base = float(base_frequency_hz)
    order_limit = int(maximum_order)
    if base <= 0 or order_limit < 1:
        raise ValueError("invalid harmonic parameters")
    if not 0.0 < tolerance_ratio < 1.0:
        raise ValueError("tolerance_ratio must be in (0, 1)")

    frequency = spectrum.frequency_hz
    amplitude = spectrum.amplitude_peak
    resolution = spectrum.resample.frequency_resolution_hz
    trusted = spectrum.resample.trusted_max_hz
    noise_floor = float(np.median(amplitude[1:])) if amplitude.size > 2 else 0.0
    threshold = max(noise_floor * float(minimum_snr), 1e-12)
    samples = spectrum.resampled_values

    entries: list[HarmonicEntry] = []
    for order in range(1, order_limit + 1):
        expected = order * base
        if expected > trusted:
            entries.append(
                HarmonicEntry(
                    order=order,
                    expected_frequency_hz=expected,
                    detected_frequency_hz=None,
                    frequency_error_hz=None,
                    amplitude_peak=None,
                    amplitude_rms=None,
                    sine_fit_amplitude=None,
                    status="NOT_RESOLVED",
                    note="above_trusted_band",
                )
            )
            continue

        tolerance = max(3.0 * resolution, tolerance_ratio * expected)
        mask = np.abs(frequency - expected) <= tolerance
        if not np.any(mask):
            entries.append(
                HarmonicEntry(
                    order=order,
                    expected_frequency_hz=expected,
                    detected_frequency_hz=None,
                    frequency_error_hz=None,
                    amplitude_peak=None,
                    amplitude_rms=None,
                    sine_fit_amplitude=None,
                    status="NOT_RESOLVED",
                    note="no_fft_bin_inside_tolerance",
                )
            )
            continue
        indices = np.flatnonzero(mask)
        local = indices[int(np.argmax(amplitude[indices]))]
        detected = float(frequency[local])
        peak = float(amplitude[local])
        fitted: float | None = None
        if samples is not None:
            first = spectrum.resample.window_start_s
            rate = spectrum.resample.sample_rate_hz
            uniform_time = first + np.arange(samples.size) / rate
            fitted = sine_fit_amplitude(uniform_time, samples, expected)

        if peak < threshold:
            status = "NOT_RESOLVED"
            note = f"below_noise_floor (peak={peak:.3e}, floor={noise_floor:.3e})"
        else:
            status = "AVAILABLE"
            note = ""
        entries.append(
            HarmonicEntry(
                order=order,
                expected_frequency_hz=expected,
                detected_frequency_hz=detected,
                frequency_error_hz=float(detected - expected),
                amplitude_peak=peak,
                amplitude_rms=float(peak / np.sqrt(2.0)),
                sine_fit_amplitude=fitted,
                status=status,
                note=note,
            )
        )
    return entries


def total_harmonic_distortion(entries: list[HarmonicEntry]) -> dict[str, Any]:
    """以实测到的各次谐波计算 THD（未解析谐波不计入）。"""
    if not entries:
        raise ValueError("empty harmonic table")
    fundamental = entries[0]
    if fundamental.status != "AVAILABLE" or not fundamental.amplitude_rms:
        return {
            "thd_percent": None,
            "status": "NOT_VERIFIED",
            "orders_used": [],
            "note": "fundamental component was not resolved",
        }
    used = [
        entry
        for entry in entries[1:]
        if entry.status == "AVAILABLE" and entry.amplitude_rms is not None
    ]
    squared = sum(float(entry.amplitude_rms) ** 2 for entry in used)
    thd = float(np.sqrt(squared) / float(fundamental.amplitude_rms) * 100.0)
    return {
        "thd_percent": thd,
        "status": "AVAILABLE",
        "orders_used": [entry.order for entry in used],
        "fundamental_rms": fundamental.amplitude_rms,
        "note": "unresolved harmonics are excluded and reported separately",
    }


def harmonic_table(entries: list[HarmonicEntry]) -> pd.DataFrame:
    """转成可直接写 CSV 的表格。"""
    return pd.DataFrame([entry.to_dict() for entry in entries])

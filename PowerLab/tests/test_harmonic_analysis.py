"""谐波表、正弦拟合与 THD 测试。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.harmonic_analysis import (
    analyze_harmonics,
    harmonic_table,
    sine_fit_amplitude,
    total_harmonic_distortion,
)
from analysis.spectrum_analysis import analyze_spectrum

F_SW = 100e3
PERIOD_S = 1.0 / F_SW


def _signal_with_harmonics(cycles: int = 100, points_per_cycle: int = 400):
    time = np.arange(0, cycles * points_per_cycle + 1, dtype=float) * (
        PERIOD_S / points_per_cycle
    )
    phase = 2.0 * np.pi * F_SW * time
    values = 5.0 + 0.1 * np.sin(phase) + 0.02 * np.sin(3.0 * phase)
    return time, values


def test_sine_fit_amplitude_is_exact_on_synthetic_sine():
    time = np.linspace(0.0, 100 * PERIOD_S, 4001)
    values = 5.0 + 0.25 * np.sin(2.0 * np.pi * F_SW * time + 0.3)
    assert sine_fit_amplitude(time, values, F_SW) == pytest.approx(0.25, rel=1e-9)
    with pytest.raises(ValueError):
        sine_fit_amplitude(time[:4], values[:4], F_SW)


def _spectrum():
    time, values = _signal_with_harmonics()
    return analyze_spectrum(
        time,
        values,
        start_s=0.0,
        end_s=float(time[-1]),
        switching_frequency_hz=F_SW,
        samples_per_cycle=200,
    )


def test_analyze_harmonics_detects_fundamental_and_third():
    entries = analyze_harmonics(_spectrum(), F_SW, maximum_order=10)
    assert len(entries) == 10
    assert [entry.order for entry in entries] == list(range(1, 11))
    fundamental = entries[0]
    third = entries[2]
    assert fundamental.status == "AVAILABLE"
    assert fundamental.amplitude_peak == pytest.approx(0.1, rel=3e-2)
    assert fundamental.frequency_error_hz == pytest.approx(0.0, abs=1e3)
    assert fundamental.sine_fit_amplitude == pytest.approx(0.1, rel=3e-2)
    assert third.status == "AVAILABLE"
    assert third.amplitude_peak == pytest.approx(0.02, rel=1e-1)
    for entry in entries:
        if entry.order in (1, 3):
            continue
        assert entry.amplitude_peak is None or entry.amplitude_peak < 5e-3
    assert harmonic_table(entries).shape[0] == 10


def test_analyze_harmonics_marks_orders_above_trusted_band():
    time = np.linspace(0.0, 20 * PERIOD_S, 501)
    values = 5.0 + 0.1 * np.sin(2.0 * np.pi * F_SW * time)
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=0.0,
        end_s=20 * PERIOD_S,
        switching_frequency_hz=F_SW,
        samples_per_cycle=200,
    )
    entries = analyze_harmonics(spectrum, F_SW, maximum_order=40)
    above = [entry for entry in entries if entry.note == "above_trusted_band"]
    assert above, "expected some harmonics above the trusted band"
    assert all(entry.status == "NOT_RESOLVED" for entry in above)


def test_total_harmonic_distortion_uses_resolved_orders():
    entries = analyze_harmonics(_spectrum(), F_SW, maximum_order=10)
    thd = total_harmonic_distortion(entries)
    assert thd["status"] == "AVAILABLE"
    assert 15.0 < thd["thd_percent"] < 25.0
    assert 3 in thd["orders_used"]
    assert "unresolved" in thd["note"]
    with pytest.raises(ValueError):
        total_harmonic_distortion([])


def test_total_harmonic_distortion_reports_unresolved_fundamental():
    time = np.linspace(0.0, 20 * PERIOD_S, 2001)
    values = 5.0 + 0.1 * np.sin(2.0 * np.pi * F_SW * time)
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=0.0,
        end_s=20 * PERIOD_S,
        switching_frequency_hz=F_SW,
        samples_per_cycle=200,
    )
    entries = analyze_harmonics(spectrum, 20e6, maximum_order=2)
    thd = total_harmonic_distortion(entries)
    assert thd["status"] == "NOT_VERIFIED"
    assert thd["thd_percent"] is None


def test_analyze_harmonics_rejects_bad_parameters():
    spectrum = _spectrum()
    with pytest.raises(ValueError):
        analyze_harmonics(spectrum, 0.0)
    with pytest.raises(ValueError):
        analyze_harmonics(spectrum, F_SW, maximum_order=0)
    with pytest.raises(ValueError):
        analyze_harmonics(spectrum, F_SW, tolerance_ratio=1.0)

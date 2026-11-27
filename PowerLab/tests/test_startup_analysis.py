"""启动过程指标测试（合成波形，不运行 SPICE）。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.startup_analysis import analyze_startup


def _startup_waveforms(duration_s: float = 2e-3, end_s: float = 20e-3):
    time = np.arange(0.0, end_s, 1e-6)
    reference = np.where(time < duration_s, 5.0 * time / duration_s, 5.0)
    voltage = 5.0 * (1.0 - np.exp(-time / 1e-3))
    inductor = np.full_like(time, 2.0)
    input_current = np.full_like(time, 1.0)
    return time, voltage, reference, inductor, input_current


def test_startup_metrics_for_smooth_rise():
    time, voltage, reference, inductor, input_current = _startup_waveforms()
    metrics = analyze_startup(
        time,
        voltage,
        reference,
        inductor,
        input_current,
        target_v=5.0,
        period_s=10e-6,
        tolerance_v=0.05,
    )
    assert metrics["rise_time_s"] > 0
    assert metrics["overshoot_percent"] < 1.0
    assert metrics["peak_inductor_current_a"] == pytest.approx(2.0)
    assert metrics["peak_input_current_a"] == pytest.approx(1.0)
    assert metrics["final_mean_v"] == pytest.approx(5.0, abs=0.01)
    assert metrics["steady_state_error_v"] == pytest.approx(0.0, abs=0.01)
    assert metrics["settling_status"] in ("OK", "INSUFFICIENT_DATA")
    assert metrics["status"] == "OK"


def test_duty_saturation_metrics():
    time, voltage, reference, _, _ = _startup_waveforms()
    duty_raw = np.where(time < 1e-3, 0.95, 0.44)
    duty_limited = np.where(time < 1e-3, 0.90, 0.44)
    metrics = analyze_startup(
        time,
        voltage,
        reference,
        target_v=5.0,
        period_s=10e-6,
        duty_raw=duty_raw,
        duty_limited=duty_limited,
    )
    assert metrics["duty_saturation_time_s"] == pytest.approx(1e-3, rel=0.02)
    assert metrics["duty_saturation_fraction"] == pytest.approx(0.05, rel=0.05)


def test_overshoot_detection():
    time = np.arange(0.0, 20e-3, 1e-6)
    voltage = 5.0 * (1.0 - np.exp(-time / 1e-3)) + 0.5 * np.exp(-((time - 3e-3) ** 2) / (2 * (0.3e-3) ** 2))
    reference = np.full_like(time, 5.0)
    metrics = analyze_startup(time, voltage, reference, target_v=5.0, period_s=10e-6)
    assert metrics["peak_voltage_v"] > 5.0
    assert metrics["overshoot_percent"] > 5.0


def test_startup_validates_inputs():
    time, voltage, reference, _, _ = _startup_waveforms()
    with pytest.raises(ValueError):
        analyze_startup(time, voltage[:-1], reference, target_v=5.0, period_s=10e-6)
    with pytest.raises(ValueError):
        analyze_startup(time[::-1], voltage, reference, target_v=5.0, period_s=10e-6)
    with pytest.raises(ValueError):
        analyze_startup(time, voltage, reference, target_v=0.0, period_s=10e-6)


def test_nonfinite_samples_are_flagged():
    time, voltage, reference, _, _ = _startup_waveforms()
    voltage = voltage.copy()
    voltage[10] = math.nan
    metrics = analyze_startup(time, voltage, reference, target_v=5.0, period_s=10e-6)
    assert metrics["status"] == "NONFINITE_SAMPLES"

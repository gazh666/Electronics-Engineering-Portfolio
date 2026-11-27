"""第六阶段指标：PWM 周期平均、CC/CV 调节精度与纹波分离。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.charging_metrics import (
    cc_regulation_metrics,
    cv_regulation_metrics,
    settling_time_s,
    switching_period_average,
)


def _ripple_waveform(frequency_hz: float = 1e5, periods: int = 5, offset: float = 0.0, amplitude: float = 0.1):
    period = 1.0 / frequency_hz
    step = period / 500.0
    time = np.arange(0.0, periods * period, step)
    phase = (time * frequency_hz) % 1.0
    values = 1.0 + offset + amplitude * (2.0 * phase - 1.0)
    return time, values


def test_period_average_separates_mean_and_ripple():
    time, values = _ripple_waveform()
    _, average, ripple, counts = switching_period_average(time, values, 1e5)
    assert average.size == 5
    assert np.allclose(average, 1.0, atol=2e-3)
    assert np.allclose(ripple, 0.2, atol=5e-3)
    assert int(counts.min()) >= 2


def test_period_average_rejects_short_record():
    time = np.array([0.0, 1e-8, 2e-8])
    values = np.array([1.0, 1.0, 1.0])
    with pytest.raises(ValueError):
        switching_period_average(time, values, 1e5)


def test_cc_metrics_zero_error_for_constant_current():
    time = np.arange(0.0, 5e-4, 2e-8)
    current = np.full(time.shape, 1.0)
    metrics = cc_regulation_metrics(time, current, 1.0, 1e5, window_s=4e-4)
    assert metrics["mean_error_a"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["ripple_pp_a"] == pytest.approx(0.0, abs=1e-9)
    assert metrics["periods"] > 10


def test_cv_metrics_reports_overshoot():
    time = np.arange(0.0, 5e-4, 2e-8)
    voltage = np.full(time.shape, 12.2)
    metrics = cv_regulation_metrics(time, voltage, 12.15, 1e5, window_s=4e-4)
    assert metrics["mean_error_v"] == pytest.approx(0.05, abs=1e-6)
    assert metrics["overshoot_v"] == pytest.approx(0.05, abs=1e-3)


def test_settling_time_uses_period_average():
    time = np.arange(0.0, 2e-3, 2e-8)
    current = np.where(time < 1e-3, 0.5, 1.0)
    settled = settling_time_s(time, current, 1.0, 0.02, frequency_hz=1e5)
    assert settled is not None
    assert settled == pytest.approx(1e-3, abs=2e-5)

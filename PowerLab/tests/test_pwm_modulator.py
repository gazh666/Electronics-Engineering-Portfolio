"""PWM 调制器与真实脉冲统计测试。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from control.pwm_modulator import (
    analyze_pwm_pulses,
    effective_duty_sine,
    measure_duty_windows,
    sawtooth_carrier,
    sine_carrier,
    sine_carrier_gain,
    threshold_from_effective_duty,
)


def test_sine_carrier_range_and_phase():
    period = 10e-6
    assert sine_carrier(0.0, 100e3) == pytest.approx(0.5)
    assert sine_carrier(period / 4.0, 100e3) == pytest.approx(1.0)
    assert sine_carrier(3.0 * period / 4.0, 100e3) == pytest.approx(0.0)


def test_sawtooth_carrier_resets_each_period():
    assert sawtooth_carrier(0.0, 100e3) == pytest.approx(0.0)
    assert sawtooth_carrier(5e-6, 100e3) == pytest.approx(0.5)
    assert sawtooth_carrier(9.999e-6, 100e3) == pytest.approx(0.9999, rel=1e-3)


def test_effective_duty_roundtrip():
    assert effective_duty_sine(0.5) == pytest.approx(0.5)
    for duty in (0.1, 0.3, 0.4448, 0.8):
        threshold = threshold_from_effective_duty(duty)
        assert effective_duty_sine(threshold) == pytest.approx(duty, abs=1e-12)


def test_sine_carrier_gain_midpoint():
    assert sine_carrier_gain(0.5) == pytest.approx(2.0 / math.pi)
    with pytest.raises(ValueError):
        sine_carrier_gain(0.0)


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_duty_helpers_reject_out_of_range(value):
    with pytest.raises(ValueError):
        threshold_from_effective_duty(value)
    with pytest.raises(ValueError):
        effective_duty_sine(value)


def test_analyze_pwm_pulses_on_square_wave():
    period = 10e-6
    time = np.arange(0.0, 40e-6, 10e-9)
    pwm = ((time % period) < 0.5 * period).astype(float)
    frame, stats = analyze_pwm_pulses(time, pwm, period)
    assert stats.cycles >= 3
    assert stats.mean_duty == pytest.approx(0.5, abs=0.01)
    assert stats.missing_pulse_cycles == 0
    assert stats.multiple_pulse_cycles == 0
    assert stats.valid is True
    assert set(frame.columns) >= {"index", "pulses", "duty"}


def test_analyze_pwm_pulses_detects_missing_pulse():
    period = 10e-6
    time = np.arange(0.0, 30e-6, 10e-9)
    pwm = np.zeros_like(time)
    _, stats = analyze_pwm_pulses(time, pwm, period)
    assert stats.missing_pulse_cycles > 0
    assert stats.valid is False


def test_analyze_pwm_pulses_validates_input():
    with pytest.raises(ValueError):
        analyze_pwm_pulses(np.array([0.0, 1e-6]), np.array([0.0, 1.0]), 10e-6)
    with pytest.raises(ValueError):
        analyze_pwm_pulses(np.array([0.0, 1e-6, 2e-6]), np.array([0.0, 1.0, 1.0]), 0.0)


def test_measure_duty_windows_returns_window_means():
    period = 10e-6
    time = np.arange(0.0, 30e-6, 10e-9)
    pwm = ((time % period) < 0.5 * period).astype(float)
    frame = measure_duty_windows(time, pwm, 10e-6)
    assert len(frame) >= 2
    assert frame["mean_duty"].between(0.4, 0.6).all()

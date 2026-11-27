"""PWM 激励参数与时间分辨率测试。"""

from __future__ import annotations

import pytest

from circuits.pwm import MIN_STEPS_PER_PERIOD, PWMParameters, validate_timing_resolution


def test_default_pwm_period_and_on_time():
    pwm = PWMParameters()
    assert pwm.period_s == pytest.approx(10e-6)
    assert pwm.target_on_time_s == pytest.approx(5.0 / 12.0 * 10e-6)
    assert pwm.threshold_voltage_v == pytest.approx(2.5)
    assert pwm.pulse_width_s == pytest.approx(pwm.target_on_time_s - 20e-9)


def test_pulse_width_subtracts_half_of_each_edge():
    pwm = PWMParameters(frequency_hz=200e3, duty_cycle=0.5, rise_time_s=50e-9, fall_time_s=50e-9)
    expected = 0.5 * pwm.period_s - 50e-9
    assert pwm.pulse_width_s == pytest.approx(expected)


def test_to_dict_contains_derived_values():
    payload = PWMParameters().to_dict()
    assert payload["period_s"] == pytest.approx(10e-6)
    assert payload["target_on_time_s"] == pytest.approx(payload["duty_cycle"] * payload["period_s"])
    assert payload["threshold_voltage_v"] == pytest.approx(2.5)


@pytest.mark.parametrize("duty", [0.0, 1.0, -0.1, 1.5])
def test_invalid_duty_cycle_rejected(duty):
    with pytest.raises(ValueError):
        PWMParameters(duty_cycle=duty)


@pytest.mark.parametrize("frequency", [0.0, -1e5, float("nan")])
def test_invalid_frequency_rejected(frequency):
    with pytest.raises(ValueError):
        PWMParameters(frequency_hz=frequency)


def test_high_level_must_exceed_low_level():
    with pytest.raises(ValueError):
        PWMParameters(low_voltage_v=5.0, high_voltage_v=5.0)


def test_edges_must_fit_inside_period():
    with pytest.raises(ValueError):
        PWMParameters(rise_time_s=6e-6, fall_time_s=6e-6)


def test_duty_too_small_for_edges_is_rejected():
    with pytest.raises(ValueError):
        PWMParameters(duty_cycle=0.001, rise_time_s=20e-9, fall_time_s=20e-9)


def test_timing_resolution_accepts_configured_step():
    steps = validate_timing_resolution(100e3, 50e-9)
    assert steps == pytest.approx(200.0)
    assert steps >= MIN_STEPS_PER_PERIOD


def test_timing_resolution_rejects_large_step():
    with pytest.raises(ValueError):
        validate_timing_resolution(100e3, 10e-6)

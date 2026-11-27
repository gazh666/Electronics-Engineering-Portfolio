"""解析理论公式（全部标记为 analytical_theory）。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.theory import (
    DATA_SOURCE,
    capacitor_stored_energy,
    diode_ideal_current,
    diode_thermal_voltage,
    half_wave_average_voltage,
    half_wave_load_power,
    half_wave_rms_voltage,
    half_wave_theory,
    inductor_stored_energy,
    rc_charging_voltage,
    rc_cutoff_frequency,
    rc_discharging_voltage,
    rc_frequency_response,
    rc_time_constant,
    rl_step_current,
    rl_time_constant,
    rlc_alpha,
    rlc_critical_resistance,
    rlc_damped_frequency,
    rlc_damping_ratio,
    rlc_frequency_response,
    rlc_natural_frequency,
    rlc_peak_frequency,
    rlc_quality_factor,
    rlc_step_overshoot_percent,
    theory_result,
    voltage_divider_current,
    voltage_divider_voltage,
)


def test_voltage_divider_theory():
    assert voltage_divider_voltage(12.0, 1_000.0, 1_000.0) == pytest.approx(6.0)
    assert voltage_divider_current(12.0, 1_000.0, 1_000.0) == pytest.approx(0.006)
    with pytest.raises(ValueError):
        voltage_divider_voltage(12.0, 0.0, 1_000.0)


def test_rc_time_constant_cutoff_and_step_response():
    tau = rc_time_constant(1_000.0, 1e-6)
    assert tau == pytest.approx(1e-3)
    assert rc_cutoff_frequency(1_000.0, 1e-6) == pytest.approx(159.15494309189535)
    assert rc_charging_voltage(1e-3, 5.0, 1_000.0, 1e-6) == pytest.approx(3.160602794, rel=1e-8)
    assert rc_discharging_voltage(1e-3, 5.0, 1_000.0, 1e-6) == pytest.approx(1.839397206, rel=1e-8)
    with pytest.raises(ValueError):
        rc_charging_voltage([-1e-3, 0.0], 5.0, 1_000.0, 1e-6)


def test_rc_frequency_response_at_cutoff():
    response = rc_frequency_response(np.array([159.15494309189535]), 1_000.0, 1e-6)
    assert response["data_source"] == DATA_SOURCE
    assert response["magnitude"][0] == pytest.approx(1 / math.sqrt(2), rel=1e-9)
    assert response["gain_db"][0] == pytest.approx(-3.0102999566, rel=1e-9)
    assert response["phase_deg"][0] == pytest.approx(-45.0)


def test_rl_theory():
    assert rl_time_constant(0.01, 10.0) == pytest.approx(1e-3)
    assert rl_step_current(1e-3, 5.0, 10.0, 0.01) == pytest.approx(0.316060279, rel=1e-8)
    assert inductor_stored_energy(0.01, 0.5) == pytest.approx(0.00125)
    assert capacitor_stored_energy(1e-6, 5.0) == pytest.approx(1.25e-5)
    with pytest.raises(ValueError):
        rl_time_constant(0.0, 10.0)


def test_rlc_derived_quantities():
    l_h, c_f = 0.01, 1e-6
    assert rlc_natural_frequency(l_h, c_f) == pytest.approx(1591.5494309189535)
    assert rlc_critical_resistance(l_h, c_f) == pytest.approx(200.0)
    assert rlc_alpha(10.0, l_h) == pytest.approx(500.0)
    assert rlc_damping_ratio(10.0, l_h, c_f) == pytest.approx(0.05)
    assert rlc_damping_ratio(200.0, l_h, c_f) == pytest.approx(1.0)
    assert rlc_damping_ratio(400.0, l_h, c_f) == pytest.approx(2.0)
    assert rlc_quality_factor(10.0, l_h, c_f) == pytest.approx(10.0)
    assert rlc_quality_factor(200.0, l_h, c_f) == pytest.approx(0.5)
    assert rlc_damped_frequency(10.0, l_h, c_f) == pytest.approx(1589.5577, rel=1e-5)
    assert rlc_damped_frequency(400.0, l_h, c_f) is None
    assert rlc_step_overshoot_percent(10.0, l_h, c_f) == pytest.approx(85.447, rel=1e-4)
    assert rlc_step_overshoot_percent(400.0, l_h, c_f) == 0.0


def test_rlc_peak_frequency_only_for_low_damping():
    assert rlc_peak_frequency(10.0, 0.01, 1e-6) == pytest.approx(1587.5656, rel=1e-5)
    assert rlc_peak_frequency(200.0, 0.01, 1e-6) is None


def test_rlc_frequency_response_peak_matches_q():
    # |H|max = 1 / (2*zeta*sqrt(1-zeta^2))，zeta=0.05 时为 10.0125
    response = rlc_frequency_response(np.array([1587.5655712767118]), 10.0, 0.01, 1e-6)
    assert response["magnitude"][0] == pytest.approx(10.012523486, rel=1e-9)
    assert response["data_source"] == DATA_SOURCE


def test_diode_theory():
    thermal = diode_thermal_voltage(25.0)
    assert thermal == pytest.approx(0.0256925791, rel=1e-6)
    assert diode_ideal_current(0.0) == pytest.approx(0.0)
    current = diode_ideal_current(0.6, 1e-9, 1.8, 25.0)
    assert current > 0.0
    with pytest.raises(ValueError):
        diode_thermal_voltage(-273.15)


def test_half_wave_rectifier_theory():
    assert half_wave_average_voltage(10.0) == pytest.approx(3.18309886)
    assert half_wave_rms_voltage(10.0) == pytest.approx(5.0)
    assert half_wave_load_power(10.0, 1_000.0) == pytest.approx(0.025)
    summary = half_wave_theory(10.0, 1_000.0)
    assert summary["data_source"] == DATA_SOURCE
    with pytest.raises(ValueError):
        half_wave_average_voltage(0.0)


def test_theory_result_marks_source():
    payload = theory_result("tau", 1e-3, "s", inputs={"r": 1_000.0}, formula="R*C")
    assert payload["data_source"] == DATA_SOURCE
    assert payload["unit"] == "s"

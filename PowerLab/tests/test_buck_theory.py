"""理想 Buck 理论公式测试（analytical_theory，不是 SPICE 数据）。"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from analysis.buck_theory import (
    boundary_load_resistance,
    calculate_ideal_buck,
    calculate_ideal_dcm,
    capacitance_for_ripple,
    duty_cycle_for_output,
    inductor_for_ripple,
)
from circuits.buck_config import BuckConfig


def test_default_buck_theory():
    result = calculate_ideal_buck(BuckConfig())
    assert result.period_s == pytest.approx(10e-6)
    assert result.duty_cycle == pytest.approx(5.0 / 12.0)
    assert result.on_time_s == pytest.approx(5.0 / 12.0 * 10e-6)
    assert result.off_time_s == pytest.approx(7.0 / 12.0 * 10e-6)
    assert result.ideal_output_voltage_v == pytest.approx(5.0)
    assert result.ideal_output_current_a == pytest.approx(2.0)
    assert result.inductor_ripple_app == pytest.approx(0.620567, rel=1e-5)
    assert result.capacitor_ripple_vpp == pytest.approx(0.0077571, rel=1e-4)
    assert result.ccm_assumption_valid
    assert result.data_source == "analytical_theory"


def test_peak_and_valley_and_boundary_values():
    result = calculate_ideal_buck(BuckConfig())
    assert result.inductor_peak_current_a == pytest.approx(
        result.ideal_output_current_a + result.boundary_current_a
    )
    assert result.inductor_valley_current_a == pytest.approx(
        result.ideal_output_current_a - result.boundary_current_a
    )
    assert result.boundary_resistance_ohm == pytest.approx(
        result.ideal_output_voltage_v / result.boundary_current_a
    )
    assert boundary_load_resistance(BuckConfig()) == pytest.approx(16.1144, rel=1e-4)


def test_ccm_assumption_fails_at_light_load():
    light = calculate_ideal_buck(BuckConfig(load_resistance_ohm=50.0))
    assert not light.ccm_assumption_valid
    assert light.inductor_valley_current_a < 0.0


def test_duty_cycle_for_output():
    assert duty_cycle_for_output(12.0, 5.0) == pytest.approx(5.0 / 12.0)
    with pytest.raises(ValueError):
        duty_cycle_for_output(5.0, 12.0)


def test_inductor_inverse_matches_forward_formula():
    duty = 5.0 / 12.0
    inductance = inductor_for_ripple(12.0, 5.0, duty, 100e3, 0.620567375886525)
    assert inductance == pytest.approx(47e-6, rel=1e-9)


def test_capacitance_inverse_matches_forward_formula():
    capacitance = capacitance_for_ripple(0.620567375886525, 100e3, 0.007757092198581563)
    assert capacitance == pytest.approx(100e-6, rel=1e-9)


def test_ideal_dcm_theory_for_light_load():
    result = calculate_ideal_dcm(BuckConfig(load_resistance_ohm=50.0))
    duty = 5.0 / 12.0
    expected_k = 2.0 * 47e-6 / (50.0 * 10e-6)
    expected_ratio = 2.0 / (1.0 + math.sqrt(1.0 + 4.0 * expected_k / duty**2))
    assert result.k == pytest.approx(expected_k)
    assert result.conversion_ratio == pytest.approx(expected_ratio)
    assert result.output_voltage_v == pytest.approx(expected_ratio * 12.0)
    assert result.boundary_k == pytest.approx(1.0 - duty)
    assert result.dcm_assumption_valid
    assert result.data_source == "analytical_theory"


def test_ideal_dcm_formula_marked_unavailable_in_ccm():
    result = calculate_ideal_dcm(BuckConfig())
    assert not result.dcm_assumption_valid


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        calculate_ideal_buck("not-a-config")
    with pytest.raises(ValueError):
        calculate_ideal_dcm(object())
    with pytest.raises(ValueError):
        inductor_for_ripple(12.0, 5.0, 1.5, 100e3, 0.6)
    with pytest.raises(ValueError):
        capacitance_for_ripple(-1.0, 100e3, 0.05)


def test_topology_parameters_affect_theory():
    baseline = calculate_ideal_buck(BuckConfig())
    larger_inductance = calculate_ideal_buck(replace(BuckConfig(), inductance_h=100e-6))
    smaller_capacitance = calculate_ideal_buck(replace(BuckConfig(), capacitance_f=47e-6))
    assert larger_inductance.inductor_ripple_app < baseline.inductor_ripple_app
    assert smaller_capacitance.capacitor_ripple_vpp > baseline.capacitor_ripple_vpp

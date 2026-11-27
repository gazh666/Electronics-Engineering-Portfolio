"""理论参考与检查口径测试。"""

from __future__ import annotations

import pytest

from validation.reference_cases import (
    build_case_config,
    diode_forward_voltage_estimate,
    load_validation_cases,
    mosfet_rds_on_estimate,
)
from validation.theoretical_validation import (
    evaluate_theory,
    ideal_ccm_theory,
    make_check,
    nonideal_ccm_theory,
    theory_reference,
)


@pytest.fixture(scope="module")
def case_config():
    case = load_validation_cases()[0]
    return case, build_case_config(case)


def test_calibrated_duty_is_recorded(case_config):
    case, config = case_config
    assert 0.3 < config.duty_cycle < 0.6
    assert config.input_voltage_v == case.input_voltage_v
    assert config.load_resistance_ohm == case.load_resistance_ohm


def test_device_estimates_are_physical(case_config):
    _, config = case_config
    assert 0.0 < mosfet_rds_on_estimate(config.mosfet) < 0.2
    assert 0.2 < diode_forward_voltage_estimate(config.diode, 2.0) < 1.0


def test_ideal_and_nonideal_output_differ(case_config):
    case, config = case_config
    theory = theory_reference(config, case)
    assert theory["ideal_ccm"]["ideal_output_voltage_v"] > config.target_output_voltage_v
    assert theory["nonideal_ccm"]["output_voltage_v"] == pytest.approx(5.0, abs=0.05)
    assert theory["ideal_ccm"]["ccm_applicability"] == "ideal CCM formula"


def test_make_check_uses_max_of_absolute_and_relative():
    passed = make_check(
        "A", "vout", 5.01, 5.0, "V", absolute_tolerance=0.02, relative_tolerance=0.0
    )
    failed = make_check(
        "B", "vout", 5.05, 5.0, "V", absolute_tolerance=0.02, relative_tolerance=0.0
    )
    assert passed.status.value == "PASS"
    assert failed.status.value == "FAIL"
    assert failed.absolute_error == pytest.approx(0.05)
    assert failed.relative_error_percent == pytest.approx(1.0)


def test_not_applicable_does_not_compute_a_verdict():
    check = make_check("C", "vout", 5.0, 5.0, "V", applicable=False)
    assert check.status.value == "NOT_APPLICABLE"
    assert check.tolerance is None


def test_missing_values_are_insufficient_data():
    check = make_check("D", "vout", None, 5.0, "V")
    assert check.status.value == "INSUFFICIENT_DATA"


def test_evaluate_theory_marks_dcm_not_applicable(case_config):
    case, config = case_config
    theory = theory_reference(config, case)
    measured = {
        "output_voltage_mean_v": 5.0,
        "inductor_current_ripple_a": 0.6,
        "inductor_current_peak_a": 2.3,
        "inductor_current_mean_a": 2.0,
        "output_voltage_ripple_vpp": 0.02,
        "inductor_current_valley_a": -0.01,
    }
    checks = evaluate_theory(measured, theory)
    assert all(check.status.value == "NOT_APPLICABLE" for check in checks)


def test_ideal_theory_ripple_formula(case_config):
    _, config = case_config
    theory = ideal_ccm_theory(config)
    ideal_vout = config.input_voltage_v * config.duty_cycle
    expected = (
        (config.input_voltage_v - ideal_vout)
        * config.duty_cycle
        / (config.inductor.inductance_h * config.switching_frequency_hz)
    )
    assert theory["ideal_output_voltage_v"] == pytest.approx(ideal_vout, rel=1e-9)
    assert theory["inductor_ripple_app"] == pytest.approx(expected, rel=1e-6)
    assert nonideal_ccm_theory(config)["inductor_ripple_app"] > 0

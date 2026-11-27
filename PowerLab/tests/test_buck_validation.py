"""Buck 验证报告结构与状态优先级测试。"""

from __future__ import annotations

import pytest

from analysis.buck_validation import (
    BuckValidationLimits,
    ValidationCheck,
    load_buck_validation_config,
    validate_buck_converter,
)
from analysis.conduction_mode import ConductionMode
from analysis.steady_state import STATUS_NOT_SETTLED, STATUS_STEADY_STATE


def _arguments(**overrides):
    payload = {
        "expected_frequency_hz": 100e3,
        "measured_frequency_hz": 100_100.0,
        "expected_duty_cycle": 5.0 / 12.0,
        "measured_duty_cycle": 5.0 / 12.0 + 0.001,
        "ideal_ccm_voltage_v": 5.0,
        "measured_output_voltage_v": 4.78,
        "ccm_assumption_valid": True,
        "theoretical_inductor_ripple_app": 0.6206,
        "measured_inductor_ripple_app": 0.64,
        "theoretical_capacitor_ripple_vpp": 0.007757,
        "measured_output_ripple_vpp": 0.0081,
        "simulated_mode": ConductionMode.CCM,
        "theoretical_mode": ConductionMode.CCM,
        "steady_state_status": STATUS_STEADY_STATE,
        "volt_second": {"relative_error": 0.001},
        "charge_balance": {"relative_error": 0.002},
        "waveform_quality_ok": True,
    }
    payload.update(overrides)
    return payload


def test_default_validation_passes_with_ten_checks():
    report = validate_buck_converter(**_arguments())
    assert report.status == "PASS"
    assert report.summary["PASS"] == 10
    names = {check.name for check in report.checks}
    assert "pwm_frequency_matches_target" in names
    assert "inductor_volt_second_balance" in names
    assert "waveform_data_quality" in names
    payload = report.to_dict()
    assert payload["data_source"] == "comparison"
    assert payload["specification_type"] == "project_assumption"


def test_frequency_mismatch_fails():
    report = validate_buck_converter(**_arguments(measured_frequency_hz=110e3))
    assert report.status == "FAIL"
    check = next(item for item in report.checks if item.name == "pwm_frequency_matches_target")
    assert check.status == "FAIL"


def test_duty_mismatch_fails():
    report = validate_buck_converter(**_arguments(measured_duty_cycle=0.5))
    assert report.status == "FAIL"


def test_dcm_marks_ccm_theory_not_applicable():
    report = validate_buck_converter(
        **_arguments(
            ccm_assumption_valid=False,
            simulated_mode=ConductionMode.DCM,
            theoretical_mode=ConductionMode.DCM,
        )
    )
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["ideal_ccm_output_voltage"] == "NOT_APPLICABLE"
    assert statuses["inductor_current_ripple"] == "NOT_APPLICABLE"
    assert statuses["output_voltage_ripple"] == "NOT_APPLICABLE"
    assert statuses["conduction_mode_matches_theory"] == "PASS"
    assert report.status == "PASS"


def test_boundary_mode_is_not_forced():
    report = validate_buck_converter(
        **_arguments(
            simulated_mode=ConductionMode.BOUNDARY_OR_UNCERTAIN,
            theoretical_mode=ConductionMode.BOUNDARY_OR_UNCERTAIN,
        )
    )
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["conduction_mode_matches_theory"] == "NOT_APPLICABLE"


def test_not_settled_is_reported_not_passed():
    report = validate_buck_converter(
        **_arguments(
            steady_state_status=STATUS_NOT_SETTLED,
            measured_output_voltage_v=None,
            measured_inductor_ripple_app=None,
            measured_output_ripple_vpp=None,
        )
    )
    assert report.status == "NOT_SETTLED"
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["ideal_ccm_output_voltage"] == "NOT_SETTLED"
    assert statuses["inductor_volt_second_balance"] == "NOT_SETTLED"


def test_balance_error_above_limit_fails():
    report = validate_buck_converter(**_arguments(volt_second={"relative_error": 0.5}))
    assert report.status == "FAIL"
    check = next(item for item in report.checks if item.name == "inductor_volt_second_balance")
    assert check.status == "FAIL"


def test_balance_without_normalization_not_applicable():
    report = validate_buck_converter(**_arguments(charge_balance={"relative_error": None}))
    check = next(item for item in report.checks if item.name == "capacitor_charge_balance")
    assert check.status == "NOT_APPLICABLE"


def test_output_ripple_design_limit_enforced():
    report = validate_buck_converter(**_arguments(measured_output_ripple_vpp=0.08))
    check = next(item for item in report.checks if item.name == "output_ripple_design_limit")
    assert check.status == "FAIL"
    assert report.status == "FAIL"


def test_waveform_quality_failure_fails():
    report = validate_buck_converter(**_arguments(waveform_quality_ok=False))
    check = next(item for item in report.checks if item.name == "waveform_data_quality")
    assert check.status == "FAIL"
    assert report.status == "FAIL"


def test_load_validation_config_from_yaml():
    limits = load_buck_validation_config()
    assert isinstance(limits, BuckValidationLimits)
    assert limits.frequency_relative_error_max == pytest.approx(0.01)
    assert limits.duty_absolute_error_max == pytest.approx(0.005)
    assert limits.output_ripple_design_limit_vpp == pytest.approx(0.05)


def test_validation_config_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_buck_validation_config(tmp_path / "missing.yaml")


def test_invalid_check_status_is_rejected():
    with pytest.raises(ValueError):
        ValidationCheck(
            name="x",
            category="y",
            status="MAYBE",
            measured=None,
            reference=None,
            error=None,
            tolerance=None,
        )


def test_invalid_mode_and_limits_types_are_rejected():
    with pytest.raises(ValueError):
        validate_buck_converter(**_arguments(simulated_mode="CCM"))
    with pytest.raises(ValueError):
        validate_buck_converter(**_arguments(limits="bad"))

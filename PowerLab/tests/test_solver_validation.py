"""SPICE 求解器设置、失败分类与对照汇总测试（不运行 ngspice）。"""

from __future__ import annotations

import pytest

from validation.models import ValidationCheck, ValidationStatus
from validation.solver_validation import (
    SolverSettings,
    classify_failure,
    compare_solver_runs,
    summarize_solver_checks,
)


def _check(status: ValidationStatus) -> ValidationCheck:
    return ValidationCheck(
        check_id=f"C-{status.value}",
        metric_name="vout",
        actual_value=5.0,
        reference_value=5.0,
        tolerance=0.001,
        unit="V",
        status=status,
        reference_type="baseline",
    )


def test_solver_settings_rejects_unknown_method():
    with pytest.raises(ValueError):
        SolverSettings(name="bad", method="euler")


def test_solver_settings_rejects_nonpositive_tolerance():
    with pytest.raises(ValueError):
        SolverSettings(name="bad", reltol=0.0)


def test_ngspice_defaults_produce_empty_spice_line():
    settings = SolverSettings(name="defaults", use_ngspice_defaults=True)
    assert settings.spice_line() == ""
    assert settings.injected_options() == []


def test_spice_line_shape():
    settings = SolverSettings(name="baseline")
    line = settings.spice_line()
    assert line.startswith(".options ")
    assert "method=trap" in line
    assert "reltol=0.0001" in line
    assert "abstol=1e-12" in line
    assert "vntol=1e-06" in line


def test_injected_options_respects_flags():
    settings = SolverSettings(name="partial", inject_reltol=False, inject_vntol=False)
    options = settings.injected_options()
    assert options == ["method", "abstol"]
    line = settings.spice_line()
    assert "reltol" not in line
    assert "vntol" not in line
    assert "method=trap" in line


def test_gear_method_is_rendered():
    settings = SolverSettings(name="gear", method="gear")
    assert "method=gear" in settings.spice_line()


def test_no_injection_flags_yields_empty_line():
    settings = SolverSettings(
        name="none",
        inject_method=False,
        inject_reltol=False,
        inject_abstol=False,
        inject_vntol=False,
    )
    assert settings.injected_options() == []
    assert settings.spice_line() == ""


def test_classify_timestep_too_small():
    result = classify_failure("Warning: Timestep too small; trouble with node")
    assert result["category"] == "timestep_too_small"
    assert result["status"] == "ERROR"
    assert "relax maximum timestep" in result["retry_advice"]


def test_classify_unknown_failure_is_not_verified():
    result = classify_failure("something unexpected happened")
    assert result["category"] == "unknown"
    assert result["status"] == ValidationStatus.NOT_VERIFIED.value


def test_compare_solver_runs_handles_error_and_completed_variants():
    baseline = {
        "output_voltage_mean_v": 5.0,
        "output_voltage_ripple_vpp": 0.02,
        "efficiency_system_percent": 90.0,
    }
    variants = [
        ("broken", {"status": "ERROR", "failure_reason": "singular matrix"}),
        ("good", dict(baseline)),
    ]
    checks = compare_solver_runs(baseline, variants)
    error_checks = [check for check in checks if check.check_id == "SOLVER-broken"]
    assert len(error_checks) == 1
    assert error_checks[0].status is ValidationStatus.ERROR
    assert error_checks[0].message == "singular matrix"
    good_checks = [check for check in checks if check.check_id.startswith("SOLVER-good-")]
    assert len(good_checks) == 3
    assert all(check.status is ValidationStatus.PASS for check in good_checks)


def test_compare_solver_runs_skips_missing_metrics():
    baseline = {"output_voltage_mean_v": 5.0}
    checks = compare_solver_runs(
        baseline,
        [("partial", {"output_voltage_mean_v": 5.0})],
    )
    assert len(checks) == 1
    assert checks[0].status is ValidationStatus.PASS


def test_summarize_precedence_error_over_fail_over_pass():
    only_pass = summarize_solver_checks([_check(ValidationStatus.PASS)])
    assert only_pass["status"] == "PASS"

    fail = summarize_solver_checks(
        [_check(ValidationStatus.PASS), _check(ValidationStatus.FAIL)]
    )
    assert fail["status"] == "FAIL"

    error = summarize_solver_checks(
        [
            _check(ValidationStatus.PASS),
            _check(ValidationStatus.FAIL),
            _check(ValidationStatus.ERROR),
        ]
    )
    assert error["status"] == "ERROR"
    assert error["counts"]["ERROR"] == 1
    assert error["counts"]["FAIL"] == 1
    assert error["counts"]["PASS"] == 1


def test_summarize_empty_is_insufficient_data():
    assert summarize_solver_checks([])["status"] == "INSUFFICIENT_DATA"

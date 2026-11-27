"""第八阶段验证数据模型测试。"""

from __future__ import annotations

import pytest

from validation.models import (
    ValidationCheck,
    ValidationResult,
    ValidationStatus,
    summarize_status,
    validate_data_source,
)


def _check(status: ValidationStatus) -> ValidationCheck:
    return ValidationCheck(
        check_id="C1",
        metric_name="vout",
        actual_value=5.0,
        reference_value=5.0,
        tolerance=0.01,
        unit="V",
        status=status,
        reference_type="analytical_theory",
    )


def test_status_values_are_explicit():
    assert ValidationStatus.PASS.value == "PASS"
    assert ValidationStatus.NOT_APPLICABLE.value == "NOT_APPLICABLE"
    assert ValidationStatus.INSUFFICIENT_DATA.value == "INSUFFICIENT_DATA"


def test_validation_check_round_trip():
    payload = _check(ValidationStatus.PASS).to_dict()
    assert payload["status"] == "PASS"
    assert payload["metric_name"] == "vout"


def test_validation_result_counts_and_evidence():
    result = ValidationResult(
        validation_id="V1",
        validation_type="theory",
        model_name="buck",
        status=ValidationStatus.PASS,
    )
    result.add(_check(ValidationStatus.PASS))
    result.add(_check(ValidationStatus.FAIL))
    result.add_run("run-1")
    result.add_run("run-1")
    assert result.counts["PASS"] == 1
    assert result.counts["FAIL"] == 1
    assert result.evidence_run_ids == ["run-1"]
    assert result.to_dict()["counts"]["FAIL"] == 1


def test_summarize_status_precedence():
    assert summarize_status([ValidationStatus.PASS]) == ValidationStatus.PASS
    assert (
        summarize_status([ValidationStatus.PASS, ValidationStatus.FAIL])
        == ValidationStatus.FAIL
    )
    assert (
        summarize_status([ValidationStatus.PASS, ValidationStatus.NOT_APPLICABLE])
        == ValidationStatus.NOT_VERIFIED
    )
    assert (
        summarize_status([ValidationStatus.NOT_APPLICABLE])
        == ValidationStatus.NOT_APPLICABLE
    )
    assert summarize_status([]) == ValidationStatus.INSUFFICIENT_DATA


def test_unknown_data_source_is_rejected():
    assert validate_data_source("spice_simulation") == "spice_simulation"
    with pytest.raises(ValueError):
        validate_data_source("made_up_source")

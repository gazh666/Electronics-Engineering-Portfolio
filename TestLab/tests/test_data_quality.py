"""数据质量检查测试：字段、功率守恒、来源、状态与重复数据。"""

import math

import pytest

from analysis.data_quality import (
    detect_duplicate_records,
    inspect_power_data,
    summarize_quality_issues,
    validate_dataset,
    validate_record,
)


def _record(**overrides):
    record = {
        "vin_setpoint": 12.0,
        "input_current_limit": 2.0,
        "load_current_setpoint": 1.0,
        "vin": 12.0,
        "iin": 5.533333333333334 / 12.0,
        "vout": 4.98,
        "iout": 1.0,
        "pin": 5.533333333333334,
        "pout": 4.98,
        "power_loss": 0.553333333333334,
        "efficiency": 0.9,
        "state": "NORMAL",
        "source": "behavioral_model",
    }
    record.update(overrides)
    return record


def test_valid_record_has_no_issues():
    quality = validate_record(_record())
    assert quality.valid
    assert quality.issues == ()


@pytest.mark.parametrize("value", [math.nan, math.inf, "abc", True])
def test_invalid_numeric_value_detected(value):
    quality = validate_record(_record(iin=value))
    assert not quality.valid
    assert {issue.code for issue in quality.issues} & {
        "INVALID_NUMBER",
        "NON_FINITE",
    }


def test_negative_value_detected():
    quality = validate_record(_record(vout=-1.0))
    assert any(issue.code == "NEGATIVE_VALUE" for issue in quality.issues)


def test_output_power_above_input_power_detected():
    record = _record(vout=6.0, pout=6.0, power_loss=-0.4666)
    quality = validate_record(record)
    assert any(issue.code == "POWER_BALANCE_ERROR" for issue in quality.issues)


def test_zero_input_power_with_load_detected():
    record = _record(iin=0.0, pin=0.0, power_loss=-4.98)
    quality = validate_record(record)
    codes = {issue.code for issue in quality.issues}
    assert "ZERO_INPUT_POWER" in codes
    assert "POWER_BALANCE_ERROR" in codes


def test_reported_power_mismatch_detected():
    quality = validate_record(_record(pin=99.0))
    assert any(issue.code == "METRIC_MISMATCH" for issue in quality.issues)


def test_reported_loss_mismatch_detected():
    quality = validate_record(_record(power_loss=0.0))
    assert any(issue.code == "METRIC_MISMATCH" for issue in quality.issues)


def test_efficiency_above_100_detected():
    record = _record(
        iin=0.5,
        pin=6.0,
        power_loss=1.0,
        efficiency=1.2,
    )
    quality = validate_record(record)
    assert any(issue.code == "EFFICIENCY_ABOVE_100" for issue in quality.issues)


def test_protection_state_with_output_detected():
    quality = validate_record(_record(state="OVERCURRENT"))
    assert any(issue.code == "STATE_OUTPUT_MISMATCH" for issue in quality.issues)


def test_protection_state_with_zero_output_is_valid():
    record = _record(
        state="OVERCURRENT",
        iin=0.0,
        vout=0.0,
        iout=0.0,
        pin=0.0,
        pout=0.0,
        power_loss=0.0,
        efficiency=None,
    )
    assert validate_record(record).valid


def test_unknown_state_detected():
    quality = validate_record(_record(state="BROKEN"))
    assert any(issue.code == "INVALID_STATE" for issue in quality.issues)


def test_source_mismatch_detected():
    quality = validate_record(_record(source="static_mock"))
    assert any(issue.code == "SOURCE_MISMATCH" for issue in quality.issues)


def test_source_check_can_be_disabled():
    quality = validate_record(_record(source="static_mock"), expected_source=None)
    assert quality.valid


def test_missing_required_field_detected():
    record = _record()
    record.pop("iin")
    quality = validate_record(record)
    assert not quality.valid
    assert any(issue.code == "MISSING_FIELD" for issue in quality.issues)


def test_missing_context_is_warning_only():
    record = _record()
    record.pop("vin_setpoint")
    record.pop("input_current_limit")
    record.pop("load_current_setpoint")
    quality = validate_record(record)
    assert quality.valid
    assert any(issue.code == "MISSING_CONTEXT" for issue in quality.issues)


def test_inspect_power_data_returns_early_on_invalid_number():
    issues = inspect_power_data(math.nan, 0.0, 0.0, 0.0)
    assert len(issues) == 1
    assert issues[0].code == "NON_FINITE"


def test_duplicate_detection_returns_groups():
    records = [_record(), _record(), _record(load_current_setpoint=2.0)]
    groups = detect_duplicate_records(records)
    assert groups == ((0, 1),)


def test_dataset_report_keeps_raw_count_and_exclusions():
    records = [_record(), _record(), _record(vout=-1.0)]
    report = validate_dataset(records)

    assert report.total_records == 3
    assert report.valid_count == 1
    assert report.valid_indices == (0,)
    assert 1 in report.excluded_indices
    assert 2 in report.excluded_indices
    assert report.excluded_count == 2
    assert any(
        issue.code == "DUPLICATE_RECORD" for issue in report.dataset_issues
    )
    payload = report.to_dict()
    assert payload["total_records"] == 3
    assert payload["excluded_count"] == 2


def test_summarize_quality_issues():
    records = [_record(), _record(source="static_mock")]
    report = validate_dataset(records, detect_duplicates=False)
    issues = [issue for record in report.records for issue in record.issues]
    summary = summarize_quality_issues(issues)
    assert summary["total"] == 1
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 0
    assert summary["by_code"] == {"SOURCE_MISMATCH": 1}

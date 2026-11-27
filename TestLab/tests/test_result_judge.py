"""判定模块单元测试。"""

import math

import pytest

from engine.models import CheckResult, TestStatus
from engine.result_judge import (
    aggregate_status,
    judge,
    judge_range,
    judge_state,
    judge_voltage,
)


def test_value_within_limits_passes():
    result = judge(5.0, 4.95, 5.05)
    assert result.passed


def test_value_below_minimum_fails():
    result = judge(4.90, 4.95, 5.05)
    assert not result.passed
    assert "下限" in result.detail


def test_value_above_maximum_fails():
    result = judge(5.10, 4.95, 5.05)
    assert not result.passed
    assert "上限" in result.detail


def test_only_maximum_limit():
    assert judge(0.2, None, 0.5).passed
    assert not judge(0.8, None, 0.5).passed


def test_nan_is_invalid():
    assert not judge(math.nan, 0.0, 1.0).passed


def test_reversed_limits_raise():
    with pytest.raises(ValueError):
        judge(1.0, 2.0, 1.0)


def test_judge_voltage_returns_pass_fail_error_strings():
    assert judge_voltage(5.0, 4.9, 5.1) == "PASS"
    assert judge_voltage(4.89, 4.9, 5.1) == "FAIL"
    assert judge_voltage(5.11, 4.9, 5.1) == "FAIL"


def test_judge_voltage_boundaries_are_inclusive():
    assert judge_voltage(4.9, 4.9, 5.1) == "PASS"
    assert judge_voltage(5.1, 4.9, 5.1) == "PASS"


def test_judge_voltage_zero_window():
    assert judge_voltage(0.0, 0.0, 0.0) == "PASS"
    assert judge_voltage(0.001, 0.0, 0.0) == "FAIL"


def test_judge_voltage_invalid_inputs_are_error():
    assert judge_voltage(math.nan, 4.9, 5.1) == "ERROR"
    assert judge_voltage(5.0, math.nan, 5.1) == "ERROR"
    assert judge_voltage(5.0, math.inf, 5.1) == "ERROR"
    assert judge_voltage(5.0, 5.1, 4.9) == "ERROR"


# ---------------------------------------------------------------------------
# 阶段七：状态、区间与汇总判定
# ---------------------------------------------------------------------------


def test_judge_state_pass_and_fail():
    passed = judge_state("NORMAL", "NORMAL")
    assert passed.status is TestStatus.PASS
    assert passed.actual == "NORMAL"

    failed = judge_state("UNDERVOLTAGE", "NORMAL")
    assert failed.status is TestStatus.FAIL
    assert "UNDERVOLTAGE" in failed.message


def test_judge_state_accepts_enum_values():
    from models.virtual_dut import DUTState

    check = judge_state(DUTState.OVERCURRENT, "OVERCURRENT")
    assert check.status is TestStatus.PASS
    assert check.actual == "OVERCURRENT"


def test_judge_range_boundaries_inclusive():
    assert judge_range("vout", 4.9, 4.9, 5.1).status is TestStatus.PASS
    assert judge_range("vout", 5.1, 4.9, 5.1).status is TestStatus.PASS
    assert judge_range("vout", 4.899, 4.9, 5.1).status is TestStatus.FAIL
    assert judge_range("vout", 5.101, 4.9, 5.1).status is TestStatus.FAIL


def test_judge_range_missing_value_is_error():
    check = judge_range("efficiency_percent", None, 85.0, 100.0)
    assert check.status is TestStatus.ERROR
    assert "缺失" in check.message


def test_judge_range_boolean_is_error():
    assert judge_range("vout", True, 0.0, 1.0).status is TestStatus.ERROR


def test_judge_range_nan_is_error():
    assert judge_range("vout", math.nan, 0.0, 1.0).status is TestStatus.ERROR


def test_judge_range_reversed_limits_raise():
    with pytest.raises(ValueError):
        judge_range("vout", 1.0, 2.0, 1.0)


def test_aggregate_status_priority():
    def check(status: TestStatus) -> CheckResult:
        return CheckResult("x", 1, 1, status)

    assert aggregate_status([check(TestStatus.PASS), check(TestStatus.FAIL)]) is TestStatus.FAIL
    assert (
        aggregate_status([check(TestStatus.FAIL), check(TestStatus.ERROR)])
        is TestStatus.ERROR
    )
    assert aggregate_status([check(TestStatus.SKIP)]) is TestStatus.SKIP
    assert aggregate_status([]) is TestStatus.ERROR

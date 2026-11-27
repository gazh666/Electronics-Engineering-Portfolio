"""结果判定与状态聚合测试。"""

from __future__ import annotations

import pytest

from validation.system_result_judge import (
    CheckResult,
    aggregate_status,
    case_status,
    compile_case_result,
    judge,
    judge_boolean,
    judge_exact,
)


def test_judge_pass_within_limits() -> None:
    result = judge("vout", 5.0, minimum=4.9, maximum=5.1)
    assert result.status == "PASS"


def test_judge_fail_out_of_range() -> None:
    assert judge("vout", 4.8, minimum=4.9).status == "FAIL"
    assert judge("soe", 101.0, maximum=100.0).status == "FAIL"


def test_missing_value_is_not_verified() -> None:
    assert judge("vout", None).status == "NOT_VERIFIED"
    assert judge("vout", float("nan")).status == "NOT_VERIFIED"


def test_boolean_and_exact_judges() -> None:
    assert judge_boolean("latched", True).status == "PASS"
    assert judge_boolean("latched", False).status == "FAIL"
    assert judge_boolean("latched", None).status == "NOT_VERIFIED"
    assert judge_exact("vout", 5.0, 5.0, 0.01).status == "PASS"


def test_aggregate_priority() -> None:
    assert aggregate_status(["PASS", "NOT_VERIFIED"]) == "NOT_VERIFIED"
    assert aggregate_status(["PASS", "FAIL", "NOT_VERIFIED"]) == "FAIL"
    assert aggregate_status(["FAIL", "ERROR"]) == "ERROR"
    assert aggregate_status([]) == "NOT_VERIFIED"


def test_case_status_without_checks_is_not_verified() -> None:
    assert case_status([]) == "NOT_VERIFIED"
    assert case_status([], execution_error="boom") == "ERROR"


def test_compile_case_result_marks_not_hardware_validated() -> None:
    payload = compile_case_result(
        case_id="SYS001", name="nominal", model_type="spice_coupled_simulation",
        run_id="run", checks=[CheckResult("vout", "PASS", 5.0, 4.9, 5.1, "V", None)],
    )
    assert payload["hardware_validated"] is False
    assert payload["status"] == "PASS"


def test_check_result_is_frozen() -> None:
    check = CheckResult("vout", "PASS", 5.0, None, None)
    with pytest.raises(Exception):
        check.status = "FAIL"  # type: ignore[misc]

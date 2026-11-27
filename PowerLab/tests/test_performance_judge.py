"""限值判定与总体状态汇总测试。"""

from __future__ import annotations

import pytest

from analysis.performance_judge import (
    judge_metric,
    judge_profile,
    overall_status,
    summarize_checks,
)
from analysis.performance_models import (
    DataSource,
    MetricStatus,
    PerformanceCheck,
    PerformanceMetric,
)


def _metric(
    value: float | None,
    status: MetricStatus = MetricStatus.AVAILABLE,
    *,
    message: str = "",
) -> PerformanceMetric:
    return PerformanceMetric(
        name="metric",
        value=value,
        unit="V",
        status=status,
        data_source=DataSource.SPICE_DERIVED,
        method="test",
        message=message,
    )


def test_judge_metric_pass_and_fail():
    rule = {"min": 0.0, "max": 1.0, "unit": "V"}
    passed = judge_metric("x", _metric(0.5), rule, profile="p")
    assert passed.status == "PASS"
    assert passed.reason == "within_limits"
    assert passed.required is False

    low = judge_metric("x", _metric(-0.1), rule)
    assert low.status == "FAIL"
    assert "below_minimum" in low.reason
    high = judge_metric("x", _metric(2.0), {"max": 1.0})
    assert high.status == "FAIL"
    assert "above_maximum" in high.reason


def test_judge_metric_handles_disabled_and_missing():
    skipped = judge_metric("x", _metric(0.5), {"enabled": False})
    assert skipped.status == "SKIP"
    assert skipped.reason == "limit_disabled"

    missing_required = judge_metric("x", None, {"required": True})
    assert missing_required.status == "ERROR"
    missing_optional = judge_metric("x", None, {"required": False})
    assert missing_optional.status == "SKIP"


def test_judge_metric_maps_data_states():
    assert (
        judge_metric("x", _metric(None, MetricStatus.NOT_APPLICABLE), {}).status
        == "NOT_APPLICABLE"
    )
    assert (
        judge_metric("x", _metric(None, MetricStatus.NOT_RESOLVED), {}).status
        == "NOT_VERIFIED"
    )
    assert (
        judge_metric("x", _metric(None, MetricStatus.NOT_SETTLED), {}).status
        == "NOT_VERIFIED"
    )
    assert (
        judge_metric("x", _metric(float("nan"), MetricStatus.INVALID_DATA), {}).status
        == "ERROR"
    )


def test_judge_profile_skips_descriptive_keys():
    metrics = {
        "x": _metric(0.5),
        "y": _metric(2.0),
    }
    profile = {
        "note": "descriptive",
        "description": "also descriptive",
        "x": {"min": 0.0, "max": 1.0},
        "y": {"min": 0.0, "max": 1.0, "required": True},
    }
    checks = judge_profile(metrics, profile, profile_name="p")
    assert [check.metric_name for check in checks] == ["x", "y"]
    assert checks[0].status == "PASS"
    assert checks[1].status == "FAIL"
    assert checks[1].required is True
    with pytest.raises(ValueError):
        judge_profile(metrics, {"bad": "not-a-mapping"})


def test_overall_status_priority():
    def check(status: str, required: bool = False) -> PerformanceCheck:
        return PerformanceCheck(
            metric_name="m",
            actual_value=1.0,
            minimum_value=None,
            maximum_value=None,
            status=status,
            reason="test",
            required=required,
        )

    assert overall_status([]) == "INCOMPLETE"
    assert overall_status([check("SKIP")]) == "INCOMPLETE"
    assert overall_status([check("PASS"), check("NOT_VERIFIED", True)]) == "INCOMPLETE"
    assert overall_status([check("PASS"), check("NOT_APPLICABLE", True)]) == "INCOMPLETE"
    assert overall_status([check("PASS"), check("NOT_APPLICABLE", False)]) == "PASS"
    assert overall_status([check("PASS"), check("FAIL")]) == "FAIL"
    assert overall_status([check("FAIL"), check("ERROR")]) == "ERROR"


def test_summarize_checks_counts_and_lists():
    checks = [
        PerformanceCheck("a", 1.0, None, None, "PASS", "ok"),
        PerformanceCheck("b", 2.0, 0.0, 1.0, "FAIL", "high"),
        PerformanceCheck("c", None, None, None, "NOT_VERIFIED", "unresolved"),
        PerformanceCheck("d", None, None, None, "NOT_APPLICABLE", "n/a"),
        PerformanceCheck("e", None, None, None, "SKIP", "disabled"),
        PerformanceCheck("f", None, None, None, "ERROR", "missing"),
    ]
    summary = summarize_checks(checks)
    assert summary["overall_status"] == "ERROR"
    assert summary["counts"] == {
        "PASS": 1,
        "FAIL": 1,
        "NOT_VERIFIED": 1,
        "NOT_APPLICABLE": 1,
        "SKIP": 1,
        "ERROR": 1,
    }
    assert summary["total"] == 6
    assert [item["metric_name"] for item in summary["failed"]] == ["b"]
    assert [item["metric_name"] for item in summary["errors"]] == ["f"]
    assert [item["metric_name"] for item in summary["not_verified"]] == ["c"]
    assert [item["metric_name"] for item in summary["skipped"]] == ["e"]

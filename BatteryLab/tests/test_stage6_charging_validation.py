"""第六阶段验收判定：预登记限值、未登记指标拒绝与预登记保护。"""

from __future__ import annotations

import pytest

from analysis.charging_validation import (
    LIMIT_SPECS,
    compare_limits,
    evaluate_limit,
    evaluate_limits,
    load_preregistered_limits,
)


def test_thirteen_preregistered_limits_loaded():
    limits = load_preregistered_limits()
    assert set(limits) == set(LIMIT_SPECS)
    assert len(limits) == 13
    assert limits["cv_mean_error_v"] == pytest.approx(0.020)
    assert limits["phase_margin_deg"] == pytest.approx(45.0)


def test_unknown_metric_is_rejected():
    limits = load_preregistered_limits()
    with pytest.raises(ValueError):
        evaluate_limits({"not_registered_metric": 1.0}, limits)


def test_over_limit_fails_and_absolute_value_applied():
    limits = load_preregistered_limits()
    report = evaluate_limits({"cv_mean_error_v": -0.03}, limits)
    result = next(item for item in report["results"] if item["name"] == "cv_mean_error_v")
    assert result["status"] == "FAIL"
    assert result["compared_value"] == pytest.approx(0.03)


def test_infinite_margin_only_allowed_for_lower_bound_metric():
    limits = load_preregistered_limits()
    report = evaluate_limits({"gain_margin_db": {"infinite": True}}, limits)
    result = next(item for item in report["results"] if item["name"] == "gain_margin_db")
    assert result["status"] == "PASS"
    with pytest.raises(ValueError):
        evaluate_limit("cc_mean_error_a", {"infinite": True}, 0.02)


def test_missing_metric_is_not_measured():
    limits = load_preregistered_limits()
    report = evaluate_limits({}, limits)
    assert report["overall_status"] == "INCOMPLETE"
    assert len(report["not_measured"]) == 13


def test_compare_limits_detects_relaxation():
    baseline = {"cv_mean_error_v": 0.02, "phase_margin_deg": 45.0}
    assert compare_limits(baseline, baseline) == []
    assert "cv_mean_error_v" in compare_limits(
        baseline, {"cv_mean_error_v": 0.05, "phase_margin_deg": 45.0}
    )
    assert "phase_margin_deg" in compare_limits(
        baseline, {"cv_mean_error_v": 0.02, "phase_margin_deg": 30.0}
    )

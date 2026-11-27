"""时间步长收敛判定与外推测试。"""

from __future__ import annotations

import pytest

from validation.convergence_analysis import (
    TimestepPoint,
    analyze_convergence,
    check_metric_convergence,
    estimate_convergence_order,
    richardson_extrapolate,
)


def _points(values_by_step: dict[float, float | None], metric: str = "vout") -> list[TimestepPoint]:
    return [
        TimestepPoint(maximum_step_s=step, metrics={metric: value})
        for step, value in values_by_step.items()
    ]


def test_stable_metric_is_numerically_stable():
    points = _points({1e-6: 5.0, 2e-6: 5.0, 4e-6: 5.001})
    result = check_metric_convergence(points, "vout", absolute_tolerance=0.01, required_pairs=2)
    assert result.status == "NUMERICALLY_STABLE"
    assert result.stable_pairs == 2
    assert result.finest_value == pytest.approx(5.0)
    assert result.finest_step_s == pytest.approx(1e-6)
    assert len(result.details) == 2


def test_unstable_metric_is_not_converged():
    points = _points({1e-6: 5.0, 2e-6: 5.1, 4e-6: 5.3})
    result = check_metric_convergence(points, "vout", absolute_tolerance=0.01, required_pairs=2)
    assert result.status == "NOT_CONVERGED"
    assert result.stable_pairs == 0
    assert result.worst_change > 1.0


def test_missing_metric_is_invalid_data():
    points = _points({1e-6: 5.0, 2e-6: None, 4e-6: 5.0})
    result = check_metric_convergence(points, "vout", absolute_tolerance=0.01)
    assert result.status == "INVALID_DATA"
    assert result.finest_value is None


def test_single_point_is_insufficient_refinement():
    result = check_metric_convergence(_points({1e-6: 5.0}), "vout")
    assert result.status == "INSUFFICIENT_REFINEMENT"


def test_estimate_order_with_uniform_ratio_is_resolved():
    points = _points({4e-6: 5.4, 2e-6: 5.2, 1e-6: 5.1})
    estimate = estimate_convergence_order(points, "vout")
    assert estimate["status"] == "RESOLVED"
    assert estimate["order"] == pytest.approx(1.0)
    assert estimate["ratio"] == pytest.approx(2.0)
    assert estimate["values"]["coarse"] == pytest.approx(5.4)
    assert estimate["values"]["medium"] == pytest.approx(5.2)
    assert estimate["values"]["fine"] == pytest.approx(5.1)


def test_estimate_order_with_non_uniform_ratio_is_not_resolved():
    points = _points({8e-6: 5.6, 2e-6: 5.2, 1e-6: 5.1})
    estimate = estimate_convergence_order(points, "vout")
    assert estimate["status"] == "NOT_RESOLVED"
    assert estimate["order"] is None
    assert "non-uniform" in estimate["reason"]


def test_estimate_order_needs_three_points():
    estimate = estimate_convergence_order(_points({2e-6: 5.2, 1e-6: 5.1}), "vout")
    assert estimate["status"] == "INSUFFICIENT_REFINEMENT"


def test_richardson_extrapolate_uses_documented_formula():
    points = _points({4e-6: 5.4, 2e-6: 5.2, 1e-6: 5.1})
    estimate = estimate_convergence_order(points, "vout")
    assert estimate["order"] == pytest.approx(1.0)
    extrapolated = richardson_extrapolate(points, "vout")
    # order=1, h1/h2=2 -> value = m2 + (m2 - m1) / (2 - 1)
    expected = 5.2 + (5.2 - 5.4) / ((4e-6 / 2e-6) ** 1.0 - 1.0)
    assert extrapolated["status"] == "EXTRAPOLATED"
    assert extrapolated["value"] == pytest.approx(expected)
    assert extrapolated["finest_value"] == pytest.approx(5.4)


def test_richardson_reports_not_resolved_for_non_uniform_grid():
    points = _points({8e-6: 5.6, 2e-6: 5.2, 1e-6: 5.1})
    extrapolated = richardson_extrapolate(points, "vout")
    assert extrapolated["status"] == "NOT_RESOLVED"
    assert extrapolated["value"] is None


def test_analyze_convergence_overall_status():
    stable_points = [
        TimestepPoint(maximum_step_s=4e-6, metrics={"vout": 5.001, "eff": 90.2}),
        TimestepPoint(maximum_step_s=2e-6, metrics={"vout": 5.0, "eff": 90.1}),
        TimestepPoint(maximum_step_s=1e-6, metrics={"vout": 5.0, "eff": 90.0}),
    ]
    rules = {"vout": {"absolute_tolerance": 0.01}, "eff": {"absolute_tolerance": 0.5}}
    report = analyze_convergence(stable_points, rules)
    assert report["overall_status"] == "NUMERICALLY_STABLE"
    assert [item["metric"] for item in report["metrics"]] == ["vout", "eff"]

    unstable_points = [
        TimestepPoint(maximum_step_s=4e-6, metrics={"vout": 5.001, "ripple": 0.3}),
        TimestepPoint(maximum_step_s=2e-6, metrics={"vout": 5.0, "ripple": 0.2}),
        TimestepPoint(maximum_step_s=1e-6, metrics={"vout": 5.0, "ripple": 0.1}),
    ]
    unstable_report = analyze_convergence(
        unstable_points,
        {"vout": {"absolute_tolerance": 0.01}, "ripple": {"absolute_tolerance": 0.001}},
    )
    assert unstable_report["overall_status"] == "NOT_CONVERGED"

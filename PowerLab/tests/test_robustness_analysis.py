"""设计鲁棒性对照与闭环角点筛查测试（不调用 SPICE）。"""

from __future__ import annotations

import pytest

from validation.corner_analysis import default_corners
from validation.models import ValidationStatus
from validation.reference_cases import build_case_config, load_validation_cases
from validation.robustness_analysis import (
    closed_loop_corner_screen,
    compare_designs,
    robustness_summary,
    summarize_closed_loop_screen,
    unavailable_design,
)
from validation.tolerance_analysis import load_component_tolerances


@pytest.fixture(scope="module")
def tolerances():
    _, mapping = load_component_tolerances()
    return mapping


def test_unavailable_design_records_gap_without_metrics():
    payload = unavailable_design("optimized_design", "stage6_missing")
    assert payload["design"] == "optimized_design"
    assert payload["status"] == ValidationStatus.NOT_APPLICABLE.value
    assert payload["known_gaps"] == "stage6_missing"
    assert "metrics" not in payload
    assert "no synthetic baseline" in payload["note"]


def test_compare_designs_present_designs_pass_and_fail():
    baseline = {
        "output_voltage_mean_v": 5.0,
        "output_voltage_ripple_vpp": 0.02,
        "efficiency_system_percent": 90.0,
    }
    identical = compare_designs(baseline, dict(baseline))
    assert {check.status.value for check in identical} == {ValidationStatus.PASS.value}
    worse_ripple = dict(baseline)
    worse_ripple["output_voltage_ripple_vpp"] = 0.03
    checks = compare_designs(baseline, worse_ripple)
    ripple = next(check for check in checks if check.metric_name == "output_voltage_ripple_vpp")
    assert ripple.status.value == ValidationStatus.FAIL.value
    assert ripple.relative_error_percent == pytest.approx(50.0)


def test_compare_designs_with_unavailable_design_is_insufficient_not_fabricated():
    baseline = {
        "output_voltage_mean_v": 5.0,
        "output_voltage_ripple_vpp": 0.02,
        "efficiency_system_percent": 90.0,
    }
    candidate = unavailable_design("optimized_design", "stage6_missing")
    checks = compare_designs(
        baseline,
        candidate,
        limit_status={"optimized_design": ValidationStatus.NOT_APPLICABLE.value},
    )
    paired = [check for check in checks if not check.check_id.startswith("RB-LIMIT")]
    assert paired and all(
        check.status.value == ValidationStatus.INSUFFICIENT_DATA.value for check in paired
    )
    assert all(check.actual_value is None for check in paired)
    limit_check = next(check for check in checks if check.check_id.startswith("RB-LIMIT"))
    assert limit_check.status.value == ValidationStatus.NOT_APPLICABLE.value


def test_summarize_closed_loop_screen_counts_evaluated_and_failed():
    rows = [
        {"corner": "nominal", "margin_status": ValidationStatus.PASS.value},
        {"corner": "all_low", "margin_status": ValidationStatus.FAIL.value},
        {"corner": "all_high", "margin_status": "NOT_RESOLVED"},
    ]
    payload = summarize_closed_loop_screen(rows)
    assert payload["evaluated"] == 2
    assert payload["failed"] == 1
    assert payload["failed_corners"] == ["all_low"]
    assert payload["status"] == ValidationStatus.FAIL.value
    assert summarize_closed_loop_screen([])["status"] == "NOT_RESOLVED"


def test_robustness_summary_structure_and_violations():
    rows = [
        {"corner": "nominal", "metrics": {"output_voltage_mean_v": 5.0}},
        {"corner": "all_high", "metrics": {"output_voltage_mean_v": 5.2}},
    ]
    payload = robustness_summary(
        rows, metric="output_voltage_mean_v", limits={"minimum": 4.9, "maximum": 5.1}
    )
    assert payload["count"] == 2
    assert payload["minimum"] == pytest.approx(5.0)
    assert payload["maximum"] == pytest.approx(5.2)
    assert payload["span"] == pytest.approx(0.2)
    assert payload["limit_status"] == ValidationStatus.FAIL.value
    assert payload["violations"] == [{"corner": "all_high", "value": 5.2}]
    assert robustness_summary([], metric="output_voltage_mean_v")["status"] == (
        ValidationStatus.INSUFFICIENT_DATA.value
    )


def test_closed_loop_corner_screen_uses_averaged_model(tolerances):
    config = build_case_config(load_validation_cases()[0])
    rows = closed_loop_corner_screen(
        config,
        tolerances,
        default_corners()[:2],
        kp=0.05,
        ki=50.0,
    )
    assert len(rows) == 2
    for row in rows:
        assert row["data_source"] == "averaged_model"
        assert row["margin_status"] in (
            ValidationStatus.PASS.value,
            ValidationStatus.FAIL.value,
            "NOT_RESOLVED",
        )
        assert "not a switching SPICE AC analysis" in row["note"]
    summary = summarize_closed_loop_screen(rows)
    assert summary["evaluated"] == 2

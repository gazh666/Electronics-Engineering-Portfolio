"""角点分析与最坏情况记录测试。"""

from __future__ import annotations

import pytest

from circuits.nonideal_config import load_nonideal_buck_config
from validation.corner_analysis import (
    Corner,
    build_corner_config,
    corner_records,
    default_corners,
    full_factorial_corners,
    summarize_corners,
    worst_corner,
)
from validation.tolerance_analysis import load_component_tolerances


@pytest.fixture(scope="module")
def tolerances():
    return load_component_tolerances()[1]


@pytest.fixture(scope="module")
def config():
    return load_nonideal_buck_config()


def test_default_corners_are_seven_named_cases():
    corners = default_corners()
    assert len(corners) == 7
    assert [corner.name for corner in corners] == [
        "nominal",
        "all_low",
        "all_high",
        "low_l_high_esr",
        "low_l_high_dcr",
        "high_low_c",
        "low_kp_high_losses",
    ]
    assert corners[0].levels == {}
    assert len(corners[1].levels) == 6
    assert corners[4].levels == {"inductance_h": "low", "inductor_dcr_ohm": "high"}


def test_corner_rejects_unknown_level():
    with pytest.raises(ValueError):
        Corner("bad", {"inductance_h": "medium"}, "invalid level")


def test_build_corner_config_changes_selected_fields(config, tolerances):
    corner = [item for item in default_corners() if item.name == "low_l_high_esr"][0]
    updated = build_corner_config(config, tolerances, corner)
    assert updated.inductor.inductance_h == pytest.approx(tolerances["inductance_h"].lower)
    assert updated.capacitor.esr_ohm == pytest.approx(tolerances["capacitor_esr_ohm"].upper)
    # 未在角点中列出的参数保持标称值。
    assert updated.capacitor.capacitance_f == pytest.approx(config.capacitor.capacitance_f)
    assert updated.inductor.dcr_ohm == pytest.approx(config.inductor.dcr_ohm)


def test_build_corner_config_nominal_keeps_config(config, tolerances):
    nominal = default_corners()[0]
    updated = build_corner_config(config, tolerances, nominal)
    assert updated == config


def test_full_factorial_corners_size_grows_by_power_of_two(tolerances):
    two = full_factorial_corners(tolerances, ["inductance_h", "capacitance_f"])
    assert len(two) == 4
    assert set(two[0]) == {"inductance_h", "capacitance_f"}
    assert all(set(entry.values()) <= {"low", "high"} for entry in two)
    three = full_factorial_corners(
        tolerances, ["inductance_h", "capacitance_f", "capacitor_esr_ohm"]
    )
    assert len(three) == 8


def test_full_factorial_corners_rejects_too_many_parameters(tolerances):
    with pytest.raises(ValueError):
        full_factorial_corners(tolerances, [])
    with pytest.raises(ValueError):
        full_factorial_corners(tolerances, list(tolerances) + ["extra_parameter"])


def test_corner_records_assign_pass_fail_and_error_statuses():
    results = [
        {"name": "ok", "metrics": {"vout": 5.0, "ripple": 0.02}},
        {"name": "bad", "metrics": {"vout": 6.0, "ripple": 0.02}},
        {"name": "err", "status": "ERROR", "failure_reason": "solver failure"},
        {"name": "missing", "metrics": {}},
    ]
    limits = {"vout": {"minimum": 4.5, "maximum": 5.5}, "ripple": {"maximum": 0.05}}
    records = corner_records(results, metric_limits=limits)
    by_name = {record["name"]: record for record in records}
    assert by_name["ok"]["limit_status"] == "PASS"
    assert by_name["bad"]["limit_status"] == "FAIL"
    assert by_name["err"]["limit_status"] == "ERROR"
    assert by_name["missing"]["limit_status"] == "NOT_VERIFIED"


def test_corner_records_without_limits_is_not_verified():
    records = corner_records([{"name": "ok", "metrics": {"vout": 5.0}}])
    assert records[0]["limit_status"] == "NOT_VERIFIED"


def test_summarize_corners_counts_statuses():
    results = [
        {"name": "ok", "metrics": {"vout": 5.0}},
        {"name": "bad", "metrics": {"vout": 6.0}},
        {"name": "err", "status": "ERROR"},
    ]
    records = corner_records(results, metric_limits={"vout": {"maximum": 5.5}})
    summary = summarize_corners(records)
    assert summary["evaluated_corners"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["errors"] == 1
    assert "not a proof of global worst case" in summary["coverage_note"]


def test_worst_corner_returns_largest_absolute_metric():
    results = [
        {"name": "ok", "metrics": {"vout": 5.0}},
        {"name": "far", "metrics": {"vout": -6.5}},
        {"name": "err", "status": "ERROR"},
    ]
    records = corner_records(results, metric_limits={"vout": {"maximum": 5.5}})
    worst = worst_corner(records, "vout")
    assert worst is not None
    assert worst["name"] == "far"
    assert worst_corner(records, "efficiency") is None

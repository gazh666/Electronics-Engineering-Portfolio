"""AFE 最坏情况误差预算单元测试（纯计算，不调用 SPICE）。"""

from __future__ import annotations

import math

import pytest

from hardening.afe_optimization import BASELINE_HISTORICAL, _load_hardening
from hardening.afe_worst_case import (
    AfeContext,
    DeviceParams,
    ErrorContribution,
    current_budget,
    current_temperature_drift,
    evaluate_error_budget,
    voltage_budget,
    voltage_temperature_drift,
)


def test_error_contributions_sum_matches_worst_case():
    items = [
        ErrorContribution("a", 1e-3, "V", "test"),
        ErrorContribution("b", 2e-3, "V", "test"),
    ]
    summary = evaluate_error_budget(items)
    assert summary["conservative_sum"] == pytest.approx(3e-3)
    assert summary["rss_magnitude"] == pytest.approx(math.sqrt(5e-6))
    assert summary["dominant"] == "b"


def test_error_contribution_rejects_unknown_unit():
    with pytest.raises(ValueError):
        ErrorContribution("bad", 1e-3, "W", "test")


def test_negative_contribution_is_counted_by_magnitude():
    summary = evaluate_error_budget([ErrorContribution("x", -2e-3, "V", "test")])
    assert summary["conservative_sum"] == pytest.approx(2e-3)


def test_afe_budget_reproduces_historical_baseline():
    context = AfeContext()
    params = DeviceParams.from_config("baseline_historical", BASELINE_HISTORICAL)
    voltage = voltage_budget(params, context)
    current = current_budget(params, context)
    assert voltage["conservative_sum"] * 1e3 == pytest.approx(30.887, abs=0.01)
    assert current["conservative_sum"] * 1e3 == pytest.approx(37.736, abs=0.01)


def test_worst_case_is_not_smaller_than_rss():
    context = AfeContext()
    params = DeviceParams.from_config("baseline_historical", BASELINE_HISTORICAL)
    voltage = voltage_budget(params, context)
    current = current_budget(params, context)
    assert voltage["conservative_sum"] >= voltage["rss_magnitude"]
    assert current["conservative_sum"] >= current["rss_magnitude"]


def test_temperature_drift_is_positive_and_reported():
    context = AfeContext()
    params = DeviceParams.from_config("baseline_historical", BASELINE_HISTORICAL)
    voltage = voltage_temperature_drift(params, context)
    current = current_temperature_drift(params, context)
    assert voltage["total_v"] > 0
    assert current["total_a"] > 0
    assert voltage["resistor_tracking_v"] > 0


def test_candidate_d_meets_both_targets_from_registered_config():
    cfg = _load_hardening()
    assert cfg["afe"]["voltage_worst_case_target_mv"] == pytest.approx(10.0)
    assert cfg["afe"]["current_worst_case_target_ma"] == pytest.approx(20.0)
    context = AfeContext()
    params = DeviceParams.from_config("D_network_low_offset_composite", cfg["afe"]["candidates"]["D_network_low_offset_composite"])
    voltage = voltage_budget(params, context)
    current = current_budget(params, context)
    assert voltage["conservative_sum"] * 1e3 <= 10.0
    assert current["conservative_sum"] * 1e3 <= 20.0
    assert voltage["conservative_sum"] * 1e3 < 30.887
    assert current["conservative_sum"] * 1e3 < 37.736

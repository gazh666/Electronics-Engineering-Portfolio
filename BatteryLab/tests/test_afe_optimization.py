"""AFE 候选优化方案单元测试：只读配置做解析预算，不调用 SPICE。"""

from __future__ import annotations

import pytest

from hardening.afe_optimization import BASELINE_HISTORICAL, _load_hardening
from hardening.afe_worst_case import AfeContext, DeviceParams, current_budget, voltage_budget


def _budgets():
    cfg = _load_hardening()
    context = AfeContext()
    result = {}
    for key, payload in cfg["afe"]["candidates"].items():
        params = DeviceParams.from_config(key, payload)
        result[key] = (
            voltage_budget(params, context)["conservative_sum"],
            current_budget(params, context)["conservative_sum"],
        )
    return cfg, result


def test_candidate_set_is_registered():
    cfg, budgets = _budgets()
    assert set(budgets) == {
        "A_original_1pct",
        "B_precision_0p1",
        "C_matched_network_0p01",
        "D_network_low_offset_composite",
    }
    assert cfg["afe"]["monte_carlo_samples"] == 1000


def test_voltage_budget_improves_monotonically_with_candidate_grade():
    _cfg, budgets = _budgets()
    order = ["A_original_1pct", "B_precision_0p1", "C_matched_network_0p01", "D_network_low_offset_composite"]
    values = [budgets[key][0] for key in order]
    assert values == sorted(values, reverse=True)
    assert values[-1] < values[0]


def test_candidate_d_is_best_for_current():
    _cfg, budgets = _budgets()
    order = ["A_original_1pct", "B_precision_0p1", "C_matched_network_0p01", "D_network_low_offset_composite"]
    values = [budgets[key][1] for key in order]
    assert min(values) == pytest.approx(budgets[order[-1]][1])


def test_only_candidates_c_and_d_meet_voltage_target():
    cfg, budgets = _budgets()
    target = cfg["afe"]["voltage_worst_case_target_mv"] / 1e3
    passing = {key for key, (voltage, _current) in budgets.items() if voltage <= target}
    assert passing == {"C_matched_network_0p01", "D_network_low_offset_composite"}


def test_historical_baseline_is_the_registered_0p1_percent_design():
    params = DeviceParams.from_config("baseline_historical", BASELINE_HISTORICAL)
    assert params.resistor_tolerance_percent == pytest.approx(0.1)

"""第七阶段实验基础设施测试（预算、限值、报告与失败记录）。"""

from __future__ import annotations

import math

import pytest

from analysis.control_comparison import evaluate_limits
from experiments import (
    STAGE7_BUDGET,
    BudgetCounter,
    load_experiment_report,
    load_transient_limits,
    summarize_failure,
)


def test_budget_counter_enforces_limits():
    counter = BudgetCounter(max_spice_runs=2, max_averaged_runs=1)
    counter.add_spice()
    counter.add_spice()
    with pytest.raises(RuntimeError):
        counter.add_spice()
    counter.add_averaged()
    with pytest.raises(RuntimeError):
        counter.add_averaged()
    payload = counter.to_dict()
    assert payload["spice_runs"] == 2
    assert payload["max_spice_runs"] == 2
    assert payload["wall_clock_s"] >= 0.0


def test_default_stage7_budget_is_explicit():
    assert STAGE7_BUDGET["spice_runs"] >= 1
    assert STAGE7_BUDGET["averaged_runs"] >= 1


def test_transient_limits_file_has_required_profiles():
    limits = load_transient_limits()
    assert limits["recovery"]["tolerance_v"] == pytest.approx(0.05)
    profiles = limits["profiles"]
    for name in (
        "nominal_closed_loop",
        "load_step_1a_to_2a",
        "load_step_generic",
        "line_step",
        "soft_start",
        "average_model_stability",
    ):
        assert name in profiles


def test_evaluate_limits_never_defaults_to_pass_on_missing_data():
    result = evaluate_limits({}, {"maximum_absolute_deviation_v": {"max": 0.3}})
    assert result["status"] == "NOT_RESOLVED"
    passed = evaluate_limits({"maximum_absolute_deviation_v": 0.2}, {"maximum_absolute_deviation_v": {"max": 0.3}})
    assert passed["status"] == "PASS"
    failed = evaluate_limits({"maximum_absolute_deviation_v": 0.4}, {"maximum_absolute_deviation_v": {"max": 0.3}})
    assert failed["status"] == "FAIL"
    nonfinite = evaluate_limits(
        {"maximum_absolute_deviation_v": math.nan},
        {"maximum_absolute_deviation_v": {"max": 0.3}},
    )
    assert nonfinite["status"] == "NOT_RESOLVED"


def test_summarize_failure_keeps_type_and_message():
    payload = summarize_failure(ValueError("bad step"))
    assert payload["status"] == "FAILED"
    assert payload["error_type"] == "ValueError"
    assert "bad step" in payload["error_message"]


def test_missing_experiment_report_raises():
    with pytest.raises(FileNotFoundError):
        load_experiment_report("__does_not_exist__")

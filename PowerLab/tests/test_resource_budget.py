"""资源预算测试（第九阶段 Task 14）。"""

from __future__ import annotations

import pytest

from jobs.resource_budget import (
    BudgetExceeded,
    JobLimits,
    check_disk_space,
    ensure_disk_space,
    ensure_within_budget,
    estimate_budget,
    load_limits,
)


def _limits(**overrides) -> JobLimits:
    payload = {
        "maximum_concurrent_jobs": 1,
        "maximum_single_job_seconds": 3600,
        "maximum_case_seconds": 300,
        "maximum_unique_spice_runs": 120,
        "maximum_monte_carlo_samples": 30,
        "maximum_plot_points": 30000,
        "minimum_free_disk_space_mb": 0,
        "maximum_log_bytes": 2_000_000,
        "profiles": {"standard": {"maximum_unique_spice_runs": 120}},
    }
    payload.update(overrides)
    return JobLimits(**payload)


def test_load_limits_from_project_config():
    limits = load_limits()
    assert limits.maximum_concurrent_jobs == 1
    assert limits.maximum_unique_spice_runs == 120
    assert limits.maximum_monte_carlo_samples == 30
    assert limits.extended_enabled() is False


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        _limits().profile("production")


def test_maximum_runs_per_profile():
    limits = _limits(profiles={"smoke": {"maximum_unique_spice_runs": 8}})
    assert limits.maximum_runs("smoke") == 8


def test_estimate_sweep_cases():
    estimate = estimate_budget(
        "parameter_sweep", {"values": [1e-6, 2e-6, 3e-6]}, _limits(), "standard"
    )
    assert estimate["planned_cases"] == 3
    assert estimate["within_budget"] is True


def test_estimate_monte_carlo_cases():
    estimate = estimate_budget("monte_carlo", {"samples": 10}, _limits(), "standard")
    assert estimate["planned_cases"] == 10


def test_estimate_validation_cases():
    estimate = estimate_budget(
        "numerical_validation", {"steps_ns": [200, 100, 50]}, _limits(), "standard"
    )
    assert estimate["planned_cases"] == 3


def test_estimate_single_case_jobs():
    estimate = estimate_budget("circuit_simulation", {}, _limits(), "standard")
    assert estimate["planned_cases"] == 1


def test_budget_exceeded_for_small_profile():
    limits = _limits(profiles={"smoke": {"maximum_unique_spice_runs": 2}})
    with pytest.raises(BudgetExceeded):
        ensure_within_budget("parameter_sweep", {"values": [1, 2, 3]}, limits, "smoke")


def test_budget_accepts_request_within_profile():
    limits = _limits(profiles={"smoke": {"maximum_unique_spice_runs": 8}})
    estimate = ensure_within_budget(
        "parameter_sweep", {"values": [1, 2, 3]}, limits, "smoke"
    )
    assert estimate["within_budget"] is True


def test_disk_space_check_reports_free_space(tmp_path):
    status = check_disk_space(tmp_path, _limits())
    assert status["ok"] is True
    assert status["free_mb"] > 0


def test_ensure_disk_space_rejects_impossible_budget(tmp_path):
    with pytest.raises(BudgetExceeded):
        ensure_disk_space(tmp_path, _limits(minimum_free_disk_space_mb=10**9))

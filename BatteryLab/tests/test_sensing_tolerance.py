"""器件容差与校准前后对照测试（Task 28/29/36）。"""

from __future__ import annotations

import pytest

from analysis.tolerance_analysis import (
    run_current_tolerance,
    run_temperature_tolerance,
    run_voltage_tolerance,
    select_corner_samples,
)
from sensing.config import load_current_sensing_config, load_ntc_config, load_tolerances
from scripts.stage4_common import afe

SAMPLE_COUNT = 20
SEED = 42


@pytest.fixture(scope="module")
def voltage_result():
    return run_voltage_tolerance(config=afe(), tolerances=load_tolerances(), sample_count=SAMPLE_COUNT, seed=SEED)


@pytest.fixture(scope="module")
def current_result():
    return run_current_tolerance(
        config=afe(),
        tolerances=load_tolerances(),
        current_config=load_current_sensing_config(),
        sample_count=SAMPLE_COUNT,
        seed=SEED,
    )


@pytest.fixture(scope="module")
def temperature_result():
    return run_temperature_tolerance(
        config=afe(),
        tolerances=load_tolerances(),
        ntc_config=load_ntc_config(),
        sample_count=SAMPLE_COUNT,
        seed=SEED,
    )


def test_voltage_sample_count_and_improvement(voltage_result):
    assert voltage_result["sample_count"] == SAMPLE_COUNT
    comparison = voltage_result["calibration_comparison"]
    assert len(voltage_result["parameter_samples"]) == SAMPLE_COUNT
    assert comparison["post_calibration"]["rmse"] <= comparison["pre_calibration"]["rmse"]
    assert comparison["improvement_percent"]["rmse"] > 0.0
    assert comparison["post_calibration"]["max_abs_error"] < 0.01


def test_voltage_calibration_uses_registered_points(voltage_result):
    assert voltage_result["calibration_points"] == [3.0, 4.1]
    assert voltage_result["validation_points"] == [2.5, 3.3, 3.7, 3.9, 4.25]


def test_current_has_zero_and_two_point_calibration(current_result):
    comparison = current_result["calibration_comparison"]
    assert "zero_calibration_only" in comparison
    post = comparison["post_calibration"]
    zero = comparison["zero_calibration_only"]
    pre = comparison["pre_calibration"]
    assert post["mae"] < zero["mae"] < pre["mae"]
    assert post["max_abs_error"] < 0.02


def test_temperature_calibration_improves(temperature_result):
    comparison = temperature_result["calibration_comparison"]
    assert comparison["post_calibration"]["rmse"] < comparison["pre_calibration"]["rmse"]
    assert comparison["post_calibration"]["max_abs_error"] < 1.0


def test_parameters_are_reproducible(voltage_result):
    repeated = run_voltage_tolerance(config=afe(), tolerances=load_tolerances(), sample_count=SAMPLE_COUNT, seed=SEED)
    assert repeated["parameter_samples"][0] == voltage_result["parameter_samples"][0]


def test_different_seed_changes_samples(voltage_result):
    other = run_voltage_tolerance(config=afe(), tolerances=load_tolerances(), sample_count=SAMPLE_COUNT, seed=SEED + 1)
    assert other["parameter_samples"][0] != voltage_result["parameter_samples"][0]


def test_corner_selection_roles(voltage_result):
    corners = select_corner_samples(voltage_result["parameter_samples"], "post_max_abs")
    assert [row["role"] for row in corners] == ["nominal", "representative", "high_error", "extreme_corner"]
    assert len({row["sample"] for row in corners}) >= 2

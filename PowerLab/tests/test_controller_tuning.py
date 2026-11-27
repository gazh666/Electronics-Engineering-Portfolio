"""控制器整定工具测试。"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from control.controller_tuning import (
    design_pi,
    evaluate_candidate,
    select_candidates,
    tuning_matrix,
)
from control.transfer_functions import TransferFunction


def test_design_pi_scales_with_plant_magnitude():
    plant = TransferFunction([1.0], [1.0, 1.0])
    result = design_pi(plant, crossover_hz=100.0, zero_hz=10.0)
    magnitude = abs(plant.evaluate(1j * 2 * math.pi * 100.0))
    expected_kp = 1.0 / (magnitude * math.sqrt(1.0 + (10.0 / 100.0) ** 2))
    assert result["kp"] == pytest.approx(expected_kp)
    assert result["ki"] == pytest.approx(2 * math.pi * 10.0 * expected_kp)
    assert result["crossover_hz"] == pytest.approx(100.0)
    assert result["zero_hz"] == pytest.approx(10.0)


def test_design_pi_rejects_invalid_inputs():
    plant = TransferFunction([1.0], [1.0, 1.0])
    with pytest.raises(ValueError):
        design_pi(plant, crossover_hz=0.0, zero_hz=10.0)
    with pytest.raises(ValueError):
        design_pi(plant, crossover_hz=100.0, zero_hz=0.0)


def test_evaluate_candidate_reports_margins_and_classification():
    plant = TransferFunction([1.0], [1.0, 1.0])
    designed = design_pi(plant, 100.0, 10.0)
    row = evaluate_candidate(plant, designed["kp"], designed["ki"])
    assert row["classification"] == "stable"
    assert row["phase_margin_deg"] > 45.0
    assert row["bandwidth_hz"] > 0
    assert row["loop_status"] == "STABLE"
    assert "messages" in row


def test_tuning_matrix_shape_order_and_columns():
    plant = TransferFunction([1.0], [1.0, 1.0])
    frame = tuning_matrix(plant, base_kp=1.0, base_ki=100.0, factors=(0.5, 1.0, 2.0))
    assert len(frame) == 9
    assert set(frame.columns) >= {
        "kp",
        "ki",
        "kp_factor",
        "ki_factor",
        "score",
        "classification",
    }
    assert frame["score"].is_monotonic_increasing
    with pytest.raises(ValueError):
        tuning_matrix(plant, 1.0, 100.0, factors=())


def test_select_candidates_limits_count_and_prefers_stable():
    frame = pd.DataFrame(
        [
            {"kp": 1.0, "ki": 10.0, "classification": "unstable", "score": 0.0},
            {"kp": 2.0, "ki": 20.0, "classification": "stable", "score": 1.0},
            {"kp": 3.0, "ki": 30.0, "classification": "stable", "score": 2.0},
            {"kp": 4.0, "ki": 40.0, "classification": "low_margin", "score": 3.0},
        ]
    )
    chosen = select_candidates(frame, count=2)
    assert len(chosen) == 2
    assert all(row["classification"] == "stable" for row in chosen)
    with pytest.raises(ValueError):
        select_candidates(frame, count=0)

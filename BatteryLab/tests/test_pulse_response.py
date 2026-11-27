"""脉冲响应分析测试。"""

from __future__ import annotations

import pytest

from analysis.pulse_response import PulseAnalysisError, analyze_pulse
from battery_models.ecm_solver import simulate_ecm
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import load_ecm_models
from battery_models.states import CellState
from simulations.load_profiles import single_pulse_profile


@pytest.fixture(scope="module")
def first_order_frame():
    definition = load_ecm_models()["first_order_rc"]
    times, currents = single_pulse_profile().sample(0.1)
    result = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.6, 1),
        times,
        currents,
        ConstantOcvModel(3.8),
        model_name="first_order_rc",
    )
    return result.frame


def test_pulse_metrics(first_order_frame) -> None:
    metrics = analyze_pulse(first_order_frame, step_time_s=10.0, release_time_s=70.0)
    assert metrics["pre_step_voltage_v"] == pytest.approx(3.8)
    assert metrics["instantaneous_voltage_after_step_v"] == pytest.approx(3.74)
    assert metrics["instantaneous_drop_v"] == pytest.approx(0.06, abs=1e-12)
    assert metrics["r0_estimate_ohm"] == pytest.approx(0.03, rel=1e-9)
    assert metrics["end_of_pulse_voltage_v"] == pytest.approx(3.7020015, abs=1e-6)
    assert metrics["recovery_jump_v"] == pytest.approx(0.06, abs=1e-5)


def test_recovery_with_long_window(first_order_frame) -> None:
    metrics = analyze_pulse(
        first_order_frame,
        step_time_s=10.0,
        release_time_s=70.0,
        tolerance_v=0.001,
        observation_window_s=120.0,
        hold_time_s=1.0,
    )
    assert metrics["recovery_status"] == "RECOVERED"
    assert 70.0 < metrics["recovery_time_s"] < 85.0


def test_recovery_marked_not_recovered_with_short_window(first_order_frame) -> None:
    metrics = analyze_pulse(
        first_order_frame,
        step_time_s=10.0,
        release_time_s=70.0,
        tolerance_v=0.001,
        observation_window_s=10.0,
    )
    assert metrics["recovery_status"] == "NOT_RECOVERED"
    assert metrics["recovery_time_s"] is None


def test_invalid_window_rejected(first_order_frame) -> None:
    with pytest.raises(PulseAnalysisError):
        analyze_pulse(first_order_frame, step_time_s=10.0, release_time_s=500.0)
    with pytest.raises(PulseAnalysisError):
        analyze_pulse(first_order_frame, step_time_s=10.0, release_time_s=70.0, tolerance_v=0.0)

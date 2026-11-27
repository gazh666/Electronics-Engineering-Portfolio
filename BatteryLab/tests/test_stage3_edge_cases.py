"""第三阶段异常与边界测试（Task 33）。

覆盖：非有限/不合理参数、时间常数顺序、优化失败状态、弱可辨识、
初始 SOC 未知、评价区间不一致、预测提前终止、验证数据重复使用。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.fitting_metrics import MetricsError, calculate_voltage_errors
from battery_models.ecm_solver import simulate_ecm
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import load_ecm_models
from battery_models.states import CellState
from identification.models import IdentifiedECMParameters, IdentificationError
from identification.parameter_validator import combine_quality, identifiability_report, validate_parameters
from validation.dataset_split import ExperimentSlice, initial_soc_from_recorded_capacity
from validation.dynamic_validation import run_open_loop_validation


def _parameters(order: int = 1, **overrides) -> IdentifiedECMParameters:
    payload = {"model_order": order, "capacity_ah": 2.0, "r0_ohm": 0.08}
    if order >= 1:
        payload.update({"r1_ohm": 0.02, "tau1_s": 20.0})
    if order >= 2:
        payload.update({"r2_ohm": 0.01, "tau2_s": 200.0})
    payload.update(overrides)
    return IdentifiedECMParameters(**payload)


def test_non_finite_parameter_rejected() -> None:
    with pytest.raises(IdentificationError):
        _parameters(r0_ohm=float("nan"))


def test_unreasonable_resistance_and_time_constant_rejected() -> None:
    with pytest.raises(IdentificationError):
        _parameters(r0_ohm=-0.01)
    with pytest.raises(IdentificationError):
        _parameters(tau1_s=-5.0)
    with pytest.raises(IdentificationError):
        _parameters(order=2, tau1_s=500.0, tau2_s=100.0)


def test_optimizer_failed_status_propagates() -> None:
    parameters = _parameters(quality_status="OPTIMIZATION_FAILED")
    report = validate_parameters(parameters, None)
    assert report["status"] == "OPTIMIZATION_FAILED"
    assert combine_quality("IDENTIFIED", "OPTIMIZATION_FAILED") == "OPTIMIZATION_FAILED"


def test_weak_identifiability_detected() -> None:
    base = np.linspace(0.0, 1.0, 80)
    jacobian = np.column_stack([base, base * 1.000001])
    report = identifiability_report(jacobian, ["r0_ohm", "r1_ohm"], condition_threshold=1.0e3)
    assert report["available"] is True
    assert report["status"] == "WEAKLY_IDENTIFIABLE"


def test_unknown_initial_soc_returns_reason() -> None:
    frame = pd.DataFrame(
        {"time_s": [0.0, 10.0, 20.0], "discharge_capacity_ah": [0.0, 2.5, 3.0]}
    )
    soc0, method = initial_soc_from_recorded_capacity(frame, 20.0, 2.0)
    assert soc0 is None
    assert method.startswith("INVALID_RESULT")


def test_evaluation_window_mismatch_raises() -> None:
    with pytest.raises(MetricsError):
        calculate_voltage_errors([1.0, 2.0, 3.0], [1.0, 2.0])


def test_prediction_not_truncated_without_limits() -> None:
    models = load_ecm_models()
    definition = models["first_order_rc"]
    time_values = np.arange(0.0, 3601.0, 60.0)
    current_values = np.full_like(time_values, 3.0)
    limited = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.05, definition.order),
        time_values,
        current_values,
        ConstantOcvModel(3.0),
        stop_on_limits=True,
    )
    unconstrained = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.05, definition.order),
        time_values,
        current_values,
        ConstantOcvModel(3.0),
        stop_on_limits=False,
    )
    assert limited.metadata["termination"] == "terminated"
    assert unconstrained.frame["time_s"].iloc[-1] == pytest.approx(time_values[-1])


def _synthetic_experiment() -> ExperimentSlice:
    count = 240
    time_values = np.arange(count, dtype=float) * 1.0
    current_values = np.where((np.arange(count) // 20) % 2 == 0, 1.0, 0.0)
    frame = pd.DataFrame(
        {
            "time_s": time_values,
            "current_a": current_values,
            "voltage_v": 3.9 - 0.05 * current_values,
            "soc_reference": 0.8 - np.cumsum(current_values) / 3600.0 / 2.0,
        }
    )
    return ExperimentSlice(
        name="synthetic_validation",
        dataset_id="synthetic_test_data",
        cell_id="TEST",
        temperature_c=25.0,
        role="synthetic_test",
        source_file="synthetic",
        source_sheet="synthetic",
        frame=frame,
        soc0=0.8,
        soc0_method="synthetic",
        capacity_ah=2.0,
        step_index=1.0,
        raw_points=count,
    )


def test_validation_does_not_tune_or_reuse_reference() -> None:
    experiment = _synthetic_experiment()
    parameters = _parameters(order=1)
    frozen = {"parameters": parameters, "ocv_model": ConstantOcvModel(3.9)}
    first = run_open_loop_validation(experiment, frozen, model_name="first_order_rc")
    second = run_open_loop_validation(experiment, frozen, model_name="first_order_rc")
    assert first["metrics"]["rmse_v"] == pytest.approx(second["metrics"]["rmse_v"])
    assert frozen["parameters"] == parameters
    # 验证电压被篡改也不会改变冻结参数或开环预测本身（指标随实测变化是正确行为）
    experiment.frame["voltage_v"] = experiment.frame["voltage_v"] + 0.02
    third = run_open_loop_validation(experiment, frozen, model_name="first_order_rc")
    assert frozen["parameters"] == parameters
    assert np.allclose(third["waveform"]["predicted_voltage_v"], second["waveform"]["predicted_voltage_v"])
    assert third["metrics"]["rmse_v"] != pytest.approx(second["metrics"]["rmse_v"])

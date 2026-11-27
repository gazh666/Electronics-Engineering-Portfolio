"""数据划分、初始 SOC 与开环验证流程。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.fitting_metrics import calculate_voltage_errors, soc_bucket_metrics
from battery_models.ocv_model import IdentifiedOcvModel
from identification.models import IdentifiedECMParameters
from validation.dataset_split import ExperimentSlice, find_dynamic_step, initial_soc_from_recorded_capacity
from validation.dynamic_validation import run_open_loop_validation, validation_table


def _raw_frame():
    time = np.concatenate(
        [
            np.arange(0.0, 60.0, 1.0),
            np.arange(60.0, 660.0, 1.0),
            np.arange(660.0, 760.0, 1.0),
            np.arange(760.0, 1660.0, 1.0),
        ]
    )
    current = np.concatenate(
        [
            np.zeros(60),
            np.full(600, 1.0),
            np.zeros(100),
            np.tile(np.array([1.0, 2.0, 0.5, 1.5, 0.0]), 180),
        ]
    )
    voltage = 3.7 - 0.02 * current + 0.001 * np.random.default_rng(0).normal(size=time.size)
    step = np.concatenate([np.zeros(60), np.ones(600), np.full(100, 2.0), np.full(900, 3.0)])
    qd = np.concatenate([np.zeros(60), np.linspace(0.0, 1.0 / 6.0, 600), np.full(100, 1.0 / 6.0), np.full(900, 1.0 / 6.0)])
    return pd.DataFrame(
        {
            "time_s": time,
            "current_a": current,
            "voltage_v": voltage,
            "step_index": step,
            "discharge_capacity_ah": qd,
            "source_file": "synthetic.xls",
            "source_sheet": "Channel_1",
        }
    )


def test_find_dynamic_step_selects_varying_current():
    frame = _raw_frame()
    dynamic = find_dynamic_step(frame)
    assert set(dynamic["step_index"]) == {3.0}
    assert len(dynamic) == 900


def test_initial_soc_from_recorded_capacity():
    frame = _raw_frame()
    soc0, method = initial_soc_from_recorded_capacity(frame, 760.0, 2.0)
    assert method == "recorded_capacity_balance"
    assert soc0 == pytest.approx(1.0 - (1.0 / 6.0) / 2.0, rel=1e-9)


def test_open_loop_validation_metrics():
    frame = _raw_frame()
    dynamic = find_dynamic_step(frame)
    dynamic = dynamic.copy()
    capacity = 2.0
    soc0 = 0.9
    cumulative = np.concatenate([[0.0], np.cumsum(dynamic["current_a"].to_numpy()[:-1] * np.diff(dynamic["time_s"].to_numpy()))]) / 3600.0
    dynamic["soc_reference"] = soc0 - cumulative / capacity
    experiment = ExperimentSlice(
        name="synthetic",
        dataset_id="synthetic",
        cell_id="SP2",
        temperature_c=25.0,
        role="independent_validation",
        source_file="synthetic.xls",
        source_sheet="Channel_1",
        frame=dynamic,
        soc0=soc0,
        soc0_method="recorded_capacity_balance",
        capacity_ah=capacity,
        step_index=3.0,
        raw_points=len(frame),
    )
    parameters = IdentifiedECMParameters.from_time_constants(
        model_order=1, capacity_ah=capacity, r0_ohm=0.02, time_constants_s=[50.0], resistances_ohm=[0.01]
    )
    frozen = {
        "parameters": parameters,
        "ocv_model": IdentifiedOcvModel(tuple(np.linspace(0, 1, 11)), tuple(np.linspace(3.0, 4.2, 11))),
    }
    result = run_open_loop_validation(experiment, frozen, model_name="first_order_rc")
    assert result["metrics"]["points"] == len(dynamic)
    assert result["metrics"]["rmse_v"] >= 0
    assert set(result["waveform"].columns) >= {"measured_voltage_v", "predicted_voltage_v", "residual_v"}
    table = validation_table({"synthetic": {"first_order_rc": result}})
    assert len(table) == 1
    buckets = soc_bucket_metrics(result["waveform"], soc_column="soc_reference")
    assert "status" in buckets.columns


def test_metrics_errors():
    with pytest.raises(ValueError):
        calculate_voltage_errors([3.8, 3.7], [3.8])
    metrics = calculate_voltage_errors([3.8, 3.7], [3.81, 3.69])
    assert metrics["points"] == 2
    assert metrics["rmse_v"] == pytest.approx(np.sqrt((0.01**2 + 0.01**2) / 2))

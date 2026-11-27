"""ECM 辨识器：ZOH 状态更新、参数恢复与 SOC 越界惩罚。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from battery_models.ocv_model import IdentifiedOcvModel
from identification.ecm_fitter import fit_single_start, multi_start_fit, ocv_callable, simulate_voltage

TRUE = {"r0_ohm": 0.030, "r1_ohm": 0.015, "tau1_s": 60.0}
OCV = IdentifiedOcvModel(tuple(np.linspace(0, 1, 21)), tuple(np.linspace(3.0, 4.2, 21)))


def _pulse_frame(duration_s=600.0, dt=1.0, capacity=2.0, soc0=0.6):
    time = np.arange(0.0, duration_s + dt, dt)
    current = np.where((time >= 50) & (time < 350), 2.0, 0.0)
    result = simulate_voltage(
        time,
        current,
        order=1,
        capacity_ah=capacity,
        soc0=soc0,
        parameters=TRUE,
        ocv=ocv_callable(OCV),
        soc_penalty_v=0.0,
    )
    return pd.DataFrame(
        {"time_s": time, "current_a": current, "voltage_v": result["voltage_v"], "soc_reference": result["soc"]}
    )


def test_simulate_matches_analytic_rc():
    time = np.array([0.0, 10.0, 20.0, 30.0])
    current = np.array([2.0, 2.0, 2.0, 2.0])
    result = simulate_voltage(
        time,
        current,
        order=1,
        capacity_ah=2.0,
        soc0=0.6,
        parameters=TRUE,
        ocv=lambda soc: 3.8,
    )
    expected_drop = TRUE["r0_ohm"] * 2.0 + TRUE["r1_ohm"] * 2.0 * (1 - np.exp(-30.0 / TRUE["tau1_s"]))
    assert result["voltage_v"][-1] == pytest.approx(3.8 - expected_drop, rel=1e-9)


def test_fit_recovers_parameters():
    frame = _pulse_frame()
    result = fit_single_start(
        frame,
        order=1,
        ocv=OCV,
        capacity_ah=2.0,
        soc0=0.6,
        initial_guess={"r0_ohm": 0.05, "r1_ohm": 0.03, "tau1_s": 150.0},
        max_nfev=120,
        dataset_id="synthetic",
    )
    assert result.fitting_success
    assert result.training_rmse_v < 1e-4
    assert result.parameter_values["r0_ohm"] == pytest.approx(TRUE["r0_ohm"], rel=0.05)
    assert result.parameter_values["r1_ohm"] == pytest.approx(TRUE["r1_ohm"], rel=0.10)
    assert result.parameter_values["tau1_s"] == pytest.approx(TRUE["tau1_s"], rel=0.15)


def test_multi_start_reports_spread():
    frame = _pulse_frame()
    result = multi_start_fit(
        frame,
        order=1,
        ocv=OCV,
        capacity_ah=2.0,
        soc0=0.6,
        initial_guesses=[
            {"r0_ohm": 0.04, "r1_ohm": 0.02, "tau1_s": 100.0},
            {"r0_ohm": 0.06, "r1_ohm": 0.04, "tau1_s": 250.0},
        ],
        max_nfev=100,
    )
    assert result["best"].training_rmse_v < 1e-4
    assert "r0_ohm" in result["spread"]
    assert len(result["all"]) == 2


def test_soc_violation_penalized():
    frame = _pulse_frame(duration_s=1000.0, soc0=0.001)
    result = simulate_voltage(
        frame["time_s"],
        frame["current_a"],
        order=0,
        capacity_ah=0.01,
        soc0=0.001,
        parameters={"r0_ohm": 0.03},
        ocv=ocv_callable(OCV),
        soc_penalty_v=0.5,
    )
    assert result["soc_violation"] > 0
    assert result["penalty_residual"] > 0

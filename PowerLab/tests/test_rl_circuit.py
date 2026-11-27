"""RL 阶跃瞬态的纸面理论与真实 ngspice 对照。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.error_metrics import time_weighted_error_metrics
from analysis.theory import DATA_SOURCE, rl_step_current, rl_time_constant
from circuits.rl_circuit import build_rl_transient
from simulations.runner import SimulationRunner

VIN_V = 5.0
RESISTANCE_OHM = 10.0
INDUCTANCE_H = 0.01
TAU_S = rl_time_constant(INDUCTANCE_H, RESISTANCE_OHM)


@pytest.fixture(scope="module")
def result():
    circuit = build_rl_transient(VIN_V, RESISTANCE_OHM, INDUCTANCE_H)
    return SimulationRunner(25.0).run_transient(circuit, 1e-5, 6e-3)


@pytest.fixture(scope="module")
def waveforms(result):
    return (
        result.data["time_s"].to_numpy(),
        result.data["l1_branch_current_a"].to_numpy(),
        -result.data["vinput_branch_current_a"].to_numpy(),
    )


def test_rl_time_constant():
    assert TAU_S == pytest.approx(1e-3)


def test_inductor_current_rises_monotonically(waveforms):
    time_s, current, supply = waveforms
    assert len(time_s) > 100
    assert np.all(np.diff(current) > -1e-9)
    assert np.all(current >= -1e-12)


def test_current_at_one_tau_and_steady_state(waveforms):
    time_s, current, _ = waveforms
    at_tau = float(np.interp(TAU_S, time_s, current))
    assert at_tau == pytest.approx(0.316060, abs=0.002)
    assert float(current[-1]) == pytest.approx(0.5, abs=0.002)


def test_supply_current_sign_is_explicit(waveforms):
    _, _, supply = waveforms
    assert supply[0] == pytest.approx(0.0, abs=1e-9)
    assert np.all(supply >= -1e-12)
    assert supply[-1] > 0.0


def test_time_weighted_error_is_small(waveforms):
    time_s, current, _ = waveforms
    theoretical = rl_step_current(time_s, VIN_V, RESISTANCE_OHM, INDUCTANCE_H)
    metrics = time_weighted_error_metrics(time_s, current, theoretical)
    assert metrics["data_source"] == "comparison"
    assert metrics["rmse_time_weighted"] < 2e-3
    assert metrics["nonuniform_sampling"] is True


def test_theory_source_is_marked():
    assert DATA_SOURCE == "analytical_theory"


def test_invalid_rl_parameters_raise():
    with pytest.raises(ValueError):
        build_rl_transient(5.0, 0.0, 0.01)
    with pytest.raises(ValueError):
        build_rl_transient(5.0, 10.0, float("nan"))

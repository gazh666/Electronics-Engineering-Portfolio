"""能量平衡测试。"""

from __future__ import annotations

import pytest

from analysis.energy_balance import energy_balance
from battery_models.ecm_solver import simulate_ecm
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import CellParameters, load_ecm_models
from battery_models.states import CellState
from simulations.load_profiles import single_pulse_profile


@pytest.fixture(scope="module")
def frames():
    models = load_ecm_models()
    profile = single_pulse_profile()
    times, currents = profile.sample(0.1)
    results = {}
    for name in ("first_order_rc", "second_order_rc"):
        definition = models[name]
        results[name] = simulate_ecm(
            definition.parameters,
            definition.branches,
            CellState.initial(0.6, definition.order),
            times,
            currents,
            ConstantOcvModel(3.8),
            model_name=name,
        ).frame
    return models, results


def test_pulse_energy_balance(frames) -> None:
    models, results = frames
    for name in ("first_order_rc", "second_order_rc"):
        definition = models[name]
        balance = energy_balance(results[name], definition.parameters, definition.branches, start_s=10.0, end_s=70.0)
        assert balance["status"] == "PASS_RELATIVE"
        assert abs(balance["relative_residual"]) <= 1e-3
        assert balance["integration_method"] == "trapezoidal"


def test_rint_energy_balance_is_exact(frames) -> None:
    models, _ = frames
    parameters = CellParameters(capacity_ah=2.0, r0_ohm=0.03)
    time_s = [0.0, 10.0, 70.0]
    current = [2.0, 2.0, 2.0]
    frame = simulate_ecm(
        parameters,
        (),
        CellState.initial(0.6, 0),
        time_s,
        current,
        ConstantOcvModel(3.8),
        stop_on_limits=False,
    ).frame
    balance = energy_balance(frame, parameters, (), start_s=0.0, end_s=70.0)
    assert balance["residual_j"] == pytest.approx(0.0, abs=1e-12)
    assert balance["status"] == "PASS_RELATIVE"


def test_rest_energy_balance(frames) -> None:
    models, results = frames
    definition = models["second_order_rc"]
    balance = energy_balance(results["second_order_rc"], definition.parameters, definition.branches, start_s=70.0, end_s=190.0)
    assert abs(balance["residual_j"]) < 1e-3
    assert balance["source_energy_j"] == pytest.approx(0.0, abs=1e-12)

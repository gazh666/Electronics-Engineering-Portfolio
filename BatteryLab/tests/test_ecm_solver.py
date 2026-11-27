"""统一 ECM 求解器测试。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from battery_models.ecm_solver import SolverError, simulate_ecm
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import CellParameters, RCBranch, load_ecm_models
from battery_models.states import CellState
from simulations.load_profiles import constant_current_profile, single_pulse_profile


@pytest.fixture(scope="module")
def models():
    return load_ecm_models()


def _run_pulse(models, name):
    definition = models[name]
    profile = single_pulse_profile()
    times, currents = profile.sample(0.1)
    return simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.6, definition.order),
        times,
        currents,
        ConstantOcvModel(3.8),
        model_name=name,
    )


def test_output_columns(models) -> None:
    result = _run_pulse(models, "second_order_rc")
    for column in (
        "time_s",
        "current_a",
        "soc",
        "ocv_v",
        "terminal_voltage_v",
        "ohmic_voltage_drop_v",
        "polarization_1_v",
        "polarization_2_v",
        "terminal_power_w",
        "ohmic_loss_w",
        "polarization_resistor_loss_w",
    ):
        assert column in result.frame.columns
    assert result.metadata["model_order"] == 2
    assert result.metadata["solver_method"] == "exact_zero_order_hold_exponential_update"


def test_rint_step_jump_is_exactly_sixty_millivolts(models) -> None:
    frame = _run_pulse(models, "rint").frame
    before = float(frame.loc[frame["time_s"] == 9.9, "terminal_voltage_v"].iloc[0])
    after = float(frame.loc[frame["time_s"] == 10.0, "terminal_voltage_v"].iloc[0])
    assert before == pytest.approx(3.8)
    assert after == pytest.approx(3.74)
    assert before - after == pytest.approx(0.06, abs=1e-12)


@pytest.mark.parametrize("name", ["first_order_rc", "second_order_rc"])
def test_rc_voltage_matches_analytic(models, name) -> None:
    frame = _run_pulse(models, name).frame
    sample_time = 69.9
    elapsed = sample_time - 10.0
    definition = models[name]
    v1 = 0.04 * (1.0 - math.exp(-elapsed / 20.0))
    v2 = 0.03 * (1.0 - math.exp(-elapsed / 60.0)) if definition.order == 2 else 0.0
    expected = 3.8 - 0.06 - v1 - v2
    actual = float(frame.loc[frame["time_s"] == sample_time, "terminal_voltage_v"].iloc[0])
    assert abs(actual - expected) < 1e-6


def test_sixty_second_pulse_reference_values(models) -> None:
    """解析参考：60 s 处一阶 3.701991 V，二阶 3.683028 V（由解析公式计算）。"""
    first = models["first_order_rc"]
    second = models["second_order_rc"]
    results = {}
    for name, definition in (("first", first), ("second", second)):
        time_s = np.array([0.0, 10.0, 70.0])
        current = np.array([0.0, 2.0, 2.0])
        result = simulate_ecm(
            definition.parameters,
            definition.branches,
            CellState.initial(0.6, definition.order),
            time_s,
            current,
            ConstantOcvModel(3.8),
            stop_on_limits=False,
        )
        results[name] = float(result.frame["terminal_voltage_v"].iloc[-1])
    assert results["first"] == pytest.approx(3.701991, abs=1e-6)
    assert results["second"] == pytest.approx(3.683028, abs=1e-6)


def test_soc_and_capacity_integration(models) -> None:
    frame = _run_pulse(models, "second_order_rc").frame
    soc_at_release = float(frame.loc[frame["time_s"] == 70.0, "soc"].iloc[0])
    assert soc_at_release == pytest.approx(0.6 - 2.0 * 60.0 / 3600.0 / 2.0, abs=1e-8)
    throughput = float(frame["capacity_throughput_ah"].iloc[-1])
    assert throughput == pytest.approx(2.0 * 60.0 / 3600.0, abs=1e-12)


def test_non_uniform_time_steps(models) -> None:
    definition = models["first_order_rc"]
    time_s = np.array([0.0, 0.1, 0.5, 2.0, 10.0, 25.0])
    current = np.full(time_s.size, 2.0)
    result = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.6, 1),
        time_s,
        current,
        ConstantOcvModel(3.8),
        stop_on_limits=False,
    )
    expected_soc = 0.6 - 2.0 * 25.0 / 3600.0 / 2.0
    assert float(result.frame["soc"].iloc[-1]) == pytest.approx(expected_soc, abs=1e-12)
    assert result.metadata["time_step"]["max_s"] == pytest.approx(15.0)


def test_soc_limit_terminates_with_event(models) -> None:
    definition = models["rint"]
    parameters = CellParameters(
        capacity_ah=0.02,
        r0_ohm=0.03,
        lower_voltage_v=3.0,
        upper_voltage_v=4.2,
    )
    profile = constant_current_profile(2.0, 100.0)
    times, currents = profile.sample(0.1)
    result = simulate_ecm(
        parameters,
        (),
        CellState.initial(0.5, 0),
        times,
        currents,
        ConstantOcvModel(3.8),
        model_name="rint",
    )
    assert result.metadata["termination"] == "terminated"
    assert result.metadata["termination_reason"] == "soc_lower_limit"
    assert result.metadata["termination_time_s"] == pytest.approx(18.0, abs=0.2)
    assert float(result.frame["soc"].iloc[-1]) == pytest.approx(0.0, abs=1e-9)
    assert any(event["event_type"] == "termination" for event in result.events)


def test_zero_resistance_and_zero_current(models) -> None:
    parameters = CellParameters(capacity_ah=2.0, r0_ohm=0.0)
    time_s = np.array([0.0, 10.0, 20.0])
    current = np.zeros(3)
    result = simulate_ecm(
        parameters,
        (),
        CellState.initial(0.6, 0),
        time_s,
        current,
        ConstantOcvModel(3.8),
        stop_on_limits=False,
    )
    assert np.allclose(result.frame["terminal_voltage_v"], 3.8)
    assert np.allclose(result.frame["soc"], 0.6)


def test_invalid_inputs_rejected(models) -> None:
    definition = models["first_order_rc"]
    with pytest.raises(SolverError):
        simulate_ecm(
            definition.parameters,
            definition.branches,
            CellState.initial(0.6, 1),
            [0.0, 1.0, 0.5],
            [0.0, 1.0, 2.0],
            ConstantOcvModel(3.8),
        )
    with pytest.raises(SolverError):
        simulate_ecm(
            definition.parameters,
            (),
            CellState.initial(0.6, 1),
            [0.0, 1.0],
            [0.0, 1.0],
            ConstantOcvModel(3.8),
        )

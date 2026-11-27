"""参数与配置校验测试。"""

from __future__ import annotations

import math

import pytest

from battery_models.parameters import (
    CellParameters,
    ECMModelDefinition,
    ParameterError,
    RCBranch,
    load_ecm_models,
    load_simulation_settings,
)


def test_load_teaching_models() -> None:
    models = load_ecm_models()
    assert set(models) == {"rint", "first_order_rc", "second_order_rc"}
    assert models["rint"].order == 0
    assert models["first_order_rc"].order == 1
    assert models["second_order_rc"].order == 2
    assert models["second_order_rc"].parameters.capacity_ah == pytest.approx(2.0)
    assert models["second_order_rc"].parameters.r0_ohm == pytest.approx(0.03)
    assert [tau for tau in models["second_order_rc"].time_constants_s] == pytest.approx([20.0, 60.0])
    assert models["rint"].parameter_source == "educational_assumption"


def test_simulation_settings_loaded() -> None:
    settings = load_simulation_settings()
    assert settings["output_step_s"] == pytest.approx(0.1)
    assert settings["duration_s"] > 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"capacity_ah": 0.0, "r0_ohm": 0.03},
        {"capacity_ah": -1.0, "r0_ohm": 0.03},
        {"capacity_ah": 2.0, "r0_ohm": -0.001},
        {"capacity_ah": 2.0, "r0_ohm": 0.03, "charge_efficiency": 0.0},
        {"capacity_ah": 2.0, "r0_ohm": 0.03, "discharge_efficiency": 1.5},
        {"capacity_ah": 2.0, "r0_ohm": 0.03, "lower_voltage_v": 4.2, "upper_voltage_v": 3.0},
        {"capacity_ah": float("nan"), "r0_ohm": 0.03},
        {"capacity_ah": True, "r0_ohm": 0.03},
    ],
)
def test_invalid_cell_parameters(kwargs: dict) -> None:
    with pytest.raises(ParameterError):
        CellParameters(**kwargs)


def test_rc_branch_validation() -> None:
    branch = RCBranch(0.02, 1000.0)
    assert branch.time_constant_s == pytest.approx(20.0)
    with pytest.raises(ParameterError):
        RCBranch(0.0, 1000.0)
    with pytest.raises(ParameterError):
        RCBranch(0.02, -1.0)
    with pytest.raises(ParameterError):
        RCBranch(float("inf"), 1000.0)


def test_model_definition_order_must_match() -> None:
    parameters = CellParameters(capacity_ah=2.0, r0_ohm=0.03)
    with pytest.raises(ParameterError):
        ECMModelDefinition("first_order_rc", parameters, ())
    with pytest.raises(ParameterError):
        ECMModelDefinition("unknown", parameters, ())


def test_parameters_are_finite_floats() -> None:
    parameters = CellParameters(capacity_ah="2.0", r0_ohm=0)
    assert math.isfinite(parameters.capacity_ah)
    assert parameters.capacity_ah == 2.0
    assert parameters.r0_ohm == 0.0

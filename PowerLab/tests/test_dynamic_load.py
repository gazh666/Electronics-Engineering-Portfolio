"""动态负载模型测试。"""

from __future__ import annotations

import pytest

from circuits.dynamic_load import (
    CurrentStep,
    CurrentStepLoad,
    ResistiveStepLoad,
    load_from_dict,
)


def test_current_step_validation():
    assert CurrentStep(time_s=0.0, current_a=0.0).current_a == 0.0
    with pytest.raises(ValueError):
        CurrentStep(time_s=-1e-3, current_a=1.0)
    with pytest.raises(ValueError):
        CurrentStep(time_s=1e-3, current_a=-1.0)


def test_current_step_load_points_and_interpolation():
    load = CurrentStepLoad(
        steps=(CurrentStep(5e-3, 2.0),),
        transition_s=20e-6,
        initial_current_a=1.0,
    )
    points = load.pwl_points(12e-3)
    assert points[0] == (0.0, 1.0)
    assert points[1] == pytest.approx((5e-3, 1.0))
    assert points[2] == pytest.approx((5e-3 + 20e-6, 2.0))
    assert points[-1] == pytest.approx((12e-3, 2.0))
    assert load.current_at(0.0) == pytest.approx(1.0)
    assert load.current_at(5.01e-3) == pytest.approx(1.5)
    assert load.current_at(5.03e-3) == pytest.approx(2.0)
    assert load.current_at(20e-3) == pytest.approx(2.0)
    assert load.peak_current_a == pytest.approx(2.0)


def test_current_step_load_rejects_bad_steps():
    with pytest.raises(ValueError):
        CurrentStepLoad(steps=())
    with pytest.raises(ValueError):
        CurrentStepLoad(
            steps=(CurrentStep(2e-3, 1.0), CurrentStep(1e-3, 2.0))
        )
    with pytest.raises(ValueError):
        CurrentStepLoad(steps=(CurrentStep(1e-3, 1.0),)).pwl_points(1e-3)


def test_resistive_step_equivalent_resistance():
    load = ResistiveStepLoad(
        base_resistance_ohm=10.0,
        target_resistance_ohm=2.5,
        step_time_s=5e-3,
        release_time_s=9e-3,
    )
    assert load.equivalent_resistance(False) == pytest.approx(10.0)
    assert load.equivalent_resistance(True) == pytest.approx(2.5)
    assert load.series_resistance_ohm > 0
    assert load.load_type == "resistive_step"


def test_resistive_step_validation():
    with pytest.raises(ValueError):
        ResistiveStepLoad(2.5, 10.0, 5e-3, 9e-3)
    with pytest.raises(ValueError):
        ResistiveStepLoad(10.0, 2.5, 9e-3, 5e-3)
    with pytest.raises(ValueError):
        ResistiveStepLoad(10.0, 2.5, 5e-3, 9e-3, switch_on_resistance_ohm=10.0)


def test_resistive_step_current_phases():
    load = ResistiveStepLoad(10.0, 2.5, 5e-3, 9e-3)
    assert load.current_at(1e-3, 5.0) == pytest.approx(0.5)
    assert load.current_at(6e-3, 5.0) == pytest.approx(2.0)
    assert load.current_at(10e-3, 5.0) == pytest.approx(0.5)


def test_load_from_dict_supports_both_types():
    current = load_from_dict(
        {
            "load_type": "constant_current",
            "initial_current_a": 1.0,
            "steps": [{"time_s": 5e-3, "current_a": 2.0}],
        }
    )
    assert isinstance(current, CurrentStepLoad)
    resistive = load_from_dict(
        {
            "load_type": "resistive_step",
            "base_resistance_ohm": 10.0,
            "target_resistance_ohm": 2.5,
            "step_time_s": 5e-3,
            "release_time_s": 9e-3,
        }
    )
    assert isinstance(resistive, ResistiveStepLoad)
    with pytest.raises(ValueError):
        load_from_dict({"load_type": "mystery"})
    with pytest.raises(ValueError):
        load_from_dict(["not", "a", "mapping"])  # type: ignore[arg-type]

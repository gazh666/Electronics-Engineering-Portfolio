"""输入电压扰动测试。"""

from __future__ import annotations

import pytest
from PySpice.Spice.Netlist import Circuit

from circuits.input_disturbance import (
    LineStepCase,
    add_input_source,
    line_cases,
    nominal_line_case,
)


def test_nominal_case_is_dc_and_spans_window():
    case = nominal_line_case(12.0)
    assert case.is_dc is True
    assert case.pwl_points(0.012) == [(0.0, 12.0), (0.012, 12.0)]
    assert case.vin_at(0.005) == pytest.approx(12.0)


def test_line_step_points_include_transition_and_release():
    case = LineStepCase(
        name="down",
        vin_initial_v=12.0,
        vin_final_v=9.0,
        step_time_s=5e-3,
        release_time_s=9e-3,
        transition_s=20e-6,
    )
    points = case.pwl_points(16e-3)
    assert points[0] == (0.0, 12.0)
    assert points[1] == pytest.approx((5e-3, 12.0))
    assert points[2] == pytest.approx((5e-3 + 20e-6, 9.0))
    assert points[3] == pytest.approx((9e-3, 9.0))
    assert points[4] == pytest.approx((9e-3 + 20e-6, 12.0))
    assert points[-1] == pytest.approx((16e-3, 12.0))
    assert case.vin_at(7e-3) == pytest.approx(9.0)
    assert case.is_dc is False


def test_line_case_validation():
    with pytest.raises(ValueError):
        LineStepCase("", 12.0, 9.0, 5e-3)
    with pytest.raises(ValueError):
        LineStepCase("bad", -1.0, 9.0, 5e-3)
    with pytest.raises(ValueError):
        LineStepCase("bad", 12.0, 9.0, 5e-3, release_time_s=1e-3)
    with pytest.raises(ValueError):
        LineStepCase("bad", 12.0, 9.0, 5e-3, transition_s=0.0)


def test_window_must_cover_release():
    case = LineStepCase("down", 12.0, 9.0, 5e-3, release_time_s=9e-3)
    with pytest.raises(ValueError):
        case.pwl_points(8e-3)


def test_add_input_source_modes():
    dc = Circuit("dc")
    layout = add_input_source(dc, nominal_line_case(12.0), 0.012)
    assert layout["mode"] == "dc"
    assert "VIN vin 0 12" in str(dc) or "VIN vin 0 DC 12" in str(dc)

    step = Circuit("step")
    case = LineStepCase("down", 12.0, 9.0, 5e-3)
    layout = add_input_source(step, case, 0.012)
    assert layout["mode"] == "pwl"
    assert str(step).count("PWL") + str(step).upper().count("PWL") > 0


def test_default_line_cases_cover_up_and_down():
    up, down = line_cases()
    assert up.vin_final_v > up.vin_initial_v
    assert down.vin_final_v < down.vin_initial_v
    assert up.is_dc is False and down.is_dc is False

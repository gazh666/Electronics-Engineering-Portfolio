"""电池供电通路解析基准测试。"""

from __future__ import annotations

import math

import pytest

from system_models.battery_power_path import incremental_resistance_ohm, solve_constant_power_load


def test_solves_high_voltage_branch() -> None:
    result = solve_constant_power_load(10.5, 0.30, 10.0)
    assert result.status == "HIGH_VOLTAGE_BRANCH"
    assert result.input_voltage_v is not None
    current = result.current_a
    assert current == pytest.approx(2.0 * 10.0 / (10.5 + math.sqrt(10.5**2 - 4 * 0.30 * 10.0)))
    assert result.input_voltage_v == pytest.approx(10.5 - current * 0.30)
    assert result.total_resistive_loss_w == pytest.approx(current**2 * 0.30)


def test_voltage_matches_power_constraint() -> None:
    result = solve_constant_power_load(11.0, 0.24, 9.0)
    assert result.input_voltage_v is not None and result.current_a is not None
    assert result.input_voltage_v * result.current_a == pytest.approx(9.0)


def test_no_operating_point_when_power_exceeds_limit() -> None:
    result = solve_constant_power_load(10.5, 0.30, 200.0)
    assert result.status == "NO_REGULAR_OPERATING_POINT"
    assert result.current_a is None
    assert result.input_voltage_v is None
    assert result.total_resistive_loss_w is None


def test_zero_resistance_is_ideal_source() -> None:
    result = solve_constant_power_load(10.0, 0.0, 10.0)
    assert result.status == "IDEAL_SOURCE"
    assert result.current_a == pytest.approx(1.0)
    assert result.input_voltage_v == pytest.approx(10.0)


def test_incremental_resistance_is_negative() -> None:
    value = incremental_resistance_ohm(10.5, 0.30, 10.0)
    assert value is not None and value < 0


@pytest.mark.parametrize("arguments", [(-1.0, 0.3, 10.0), (10.5, -0.1, 10.0), (10.5, 0.3, -1.0),
                                       (float("nan"), 0.3, 10.0)])
def test_invalid_inputs_raise(arguments) -> None:
    with pytest.raises(ValueError):
        solve_constant_power_load(*arguments)

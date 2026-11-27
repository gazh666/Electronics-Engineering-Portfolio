"""参数校验与单位边界测试。"""

from __future__ import annotations

import math

import pytest

from circuits.validators import (
    MAX_DC_SWEEP_POINTS,
    ac_sweep,
    dc_sweep,
    finite_number,
    nonnegative_number,
    positive_integer,
    positive_number,
    strictly_increasing,
    temperature_celsius,
    transient_parameters,
)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, "1.0", None])
def test_finite_number_rejects_non_numeric(bad):
    with pytest.raises(ValueError):
        finite_number(bad, "value")


def test_finite_number_allows_negative():
    assert finite_number(-2.5, "value") == -2.5


def test_positive_number_rejects_zero_and_negative():
    with pytest.raises(ValueError):
        positive_number(0.0, "r")
    with pytest.raises(ValueError):
        positive_number(-1.0, "r")


def test_nonnegative_number_accepts_zero():
    assert nonnegative_number(0, "x") == 0.0


def test_positive_integer_rejects_bool_and_float():
    with pytest.raises(ValueError):
        positive_integer(True, "n")
    with pytest.raises(ValueError):
        positive_integer(2.0, "n")
    assert positive_integer(3, "n") == 3


def test_temperature_must_be_above_absolute_zero():
    assert temperature_celsius(25.0) == 25.0
    with pytest.raises(ValueError):
        temperature_celsius(-273.15)


def test_dc_sweep_accepts_ascending_and_descending():
    assert dc_sweep(0.0, 12.0, 0.5) == (0.0, 12.0, 0.5)
    assert dc_sweep(1.0, -1.0, -0.1) == (1.0, -1.0, -0.1)
    descending = dc_sweep(-1.0, -2.0, -0.1)
    assert descending[2] < 0


def test_dc_sweep_rejects_wrong_direction_and_zero_step():
    with pytest.raises(ValueError):
        dc_sweep(0.0, 1.0, -0.1)
    with pytest.raises(ValueError):
        dc_sweep(0.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        dc_sweep(0.0, 0.0, 0.1)


def test_dc_sweep_rejects_too_many_points():
    step = 12.0 / (MAX_DC_SWEEP_POINTS + 10)
    with pytest.raises(ValueError):
        dc_sweep(0.0, 12.0, step)


def test_transient_parameters_order_and_limits():
    start, end, step = transient_parameters(1e-5, 1e-3, 0.0)
    assert (start, end, step) == (0.0, 1e-3, 1e-5)
    with pytest.raises(ValueError):
        transient_parameters(1e-3, 1e-3, 0.0)
    with pytest.raises(ValueError):
        transient_parameters(1e-5, 1e-3, -1.0)


def test_ac_sweep_validates_range_and_points():
    assert ac_sweep(1.0, 1e5, 50) == (1.0, 1e5, 50, "dec")
    with pytest.raises(ValueError):
        ac_sweep(1e5, 1.0, 50)
    with pytest.raises(ValueError):
        ac_sweep(1.0, 1e5, 0)
    with pytest.raises(ValueError):
        ac_sweep(1.0, 1e5, 50, variation="bad")


def test_strictly_increasing_detects_duplicates_and_nan():
    strictly_increasing([0.0, 1.0, 2.0], "time")
    with pytest.raises(ValueError):
        strictly_increasing([0.0, 0.0, 1.0], "time")
    with pytest.raises(ValueError):
        strictly_increasing([0.0, math.nan], "time")

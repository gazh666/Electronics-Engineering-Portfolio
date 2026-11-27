"""安时积分单元测试。"""

from __future__ import annotations

import math

import pytest

from estimation.coulomb_counter import CoulombCounter, CoulombCounterError


def test_constant_discharge_matches_analytic_solution():
    counter = CoulombCounter(capacity_ah=2.0, soc=1.0)
    update = counter.step(1.0, 3600.0)
    assert math.isclose(update.soc, 0.5, abs_tol=1e-12)
    assert math.isclose(update.delta_soc, -0.5, abs_tol=1e-12)
    assert update.status == "VALID"


def test_charge_efficiency_applied_on_charge_only():
    counter = CoulombCounter(capacity_ah=2.0, soc=0.5, charge_efficiency=0.9)
    update = counter.step(-1.0, 3600.0)
    assert math.isclose(update.soc, 0.5 + 0.9 * 0.5, abs_tol=1e-12)


def test_lower_bound_is_recorded_not_hidden():
    counter = CoulombCounter(capacity_ah=2.0, soc=0.01)
    update = counter.step(1.0, 3600.0)
    assert update.soc == 0.0
    assert update.raw_soc < 0.0
    assert update.status == "SOC_BOUND_REACHED"
    assert counter.bound_count == 1


def test_invalid_inputs_raise():
    with pytest.raises(CoulombCounterError):
        CoulombCounter(capacity_ah=0.0, soc=0.5)
    with pytest.raises(CoulombCounterError):
        CoulombCounter(capacity_ah=2.0, soc=1.2)
    counter = CoulombCounter(capacity_ah=2.0, soc=0.5)
    with pytest.raises(CoulombCounterError):
        counter.step(1.0, 0.0)
    with pytest.raises(CoulombCounterError):
        counter.step(float("nan"), 1.0)

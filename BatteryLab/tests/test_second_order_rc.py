"""二阶 RC 模型测试。"""

from __future__ import annotations

import math

import pytest

from battery_models.second_order_rc import (
    SecondOrderRcError,
    calculate_polarization_losses,
    calculate_stored_energies,
    calculate_time_constants,
    second_order_terminal_voltage,
    update_second_order_polarization,
)


def test_two_time_constants() -> None:
    tau1, tau2 = calculate_time_constants(0.02, 1000.0, 0.015, 4000.0)
    assert tau1 == pytest.approx(20.0)
    assert tau2 == pytest.approx(60.0)
    assert tau1 != tau2


def test_exact_updates_match_analytic() -> None:
    v1, v2 = update_second_order_polarization(0.0, 0.0, 2.0, 0.02, 1000.0, 0.015, 4000.0, 60.0)
    assert v1 == pytest.approx(0.04 * (1.0 - math.exp(-3.0)), abs=1e-12)
    assert v2 == pytest.approx(0.03 * (1.0 - math.exp(-1.0)), abs=1e-12)
    assert v2 == pytest.approx(0.018964, abs=1e-6)


def test_terminal_voltage_subtracts_both_branches() -> None:
    voltage = second_order_terminal_voltage(3.8, 2.0, 0.03, 0.038009, 0.018964)
    assert voltage == pytest.approx(3.8 - 0.06 - 0.038009 - 0.018964)


def test_branch_losses_and_energies() -> None:
    losses = calculate_polarization_losses(0.02, 0.038, 0.015, 0.019)
    assert losses[0] == pytest.approx(0.038**2 / 0.02)
    assert losses[1] == pytest.approx(0.019**2 / 0.015)
    energies = calculate_stored_energies(1000.0, 0.038, 4000.0, 0.019)
    assert energies[0] == pytest.approx(0.5 * 1000.0 * 0.038**2)
    assert energies[1] == pytest.approx(0.5 * 4000.0 * 0.019**2)


def test_charge_current_produces_negative_polarization() -> None:
    v1, v2 = update_second_order_polarization(0.0, 0.0, -1.0, 0.02, 1000.0, 0.015, 4000.0, 30.0)
    assert v1 < 0.0
    assert v2 < 0.0
    voltage = second_order_terminal_voltage(3.8, -1.0, 0.03, v1, v2)
    assert voltage > 3.8


def test_invalid_parameters_rejected() -> None:
    with pytest.raises(SecondOrderRcError):
        calculate_time_constants(0.02, 0.0, 0.015, 4000.0)
    with pytest.raises(SecondOrderRcError):
        calculate_polarization_losses(0.0, 0.01, 0.015, 0.01)
    with pytest.raises(SecondOrderRcError):
        calculate_stored_energies(1000.0, 0.01, -4000.0, 0.01)

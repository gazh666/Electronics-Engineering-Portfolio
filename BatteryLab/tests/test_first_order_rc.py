"""一阶 RC 精确更新测试。"""

from __future__ import annotations

import math

import pytest

from battery_models.first_order_rc import (
    FirstOrderRcError,
    calculate_polarization_loss,
    calculate_stored_energy,
    calculate_time_constant,
    first_order_terminal_voltage,
    polarization_fraction,
    update_first_order_polarization,
)


def test_time_constant() -> None:
    assert calculate_time_constant(0.02, 1000.0) == pytest.approx(20.0)


def test_exact_update_matches_analytic_at_one_tau() -> None:
    tau = 20.0
    voltage = update_first_order_polarization(0.0, 2.0, 0.02, 1000.0, tau)
    expected = 2.0 * 0.02 * (1.0 - math.exp(-1.0))
    assert voltage == pytest.approx(expected, abs=1e-12)
    assert voltage / 0.04 == pytest.approx(0.6321, abs=1e-4)


def test_repeated_small_steps_match_single_step() -> None:
    total = 0.0
    steps = 200
    dt = 20.0 / steps
    for _ in range(steps):
        total = update_first_order_polarization(total, 2.0, 0.02, 1000.0, dt)
    expected = update_first_order_polarization(0.0, 2.0, 0.02, 1000.0, 20.0)
    assert total == pytest.approx(expected, abs=1e-12)


def test_extremely_small_step_is_stable() -> None:
    voltage = update_first_order_polarization(0.0, 2.0, 0.02, 1000.0, 1e-9)
    expected = 2.0 * 0.02 * (1.0 - math.exp(-1e-9 / 20.0))
    assert voltage == pytest.approx(expected, rel=1e-12, abs=1e-18)


def test_zero_current_decays_towards_zero() -> None:
    voltage = 0.04
    for _ in range(3):
        voltage = update_first_order_polarization(voltage, 0.0, 0.02, 1000.0, 20.0)
    assert voltage == pytest.approx(0.04 * math.exp(-3.0), abs=1e-12)


def test_polarization_fractions() -> None:
    assert polarization_fraction(1.0, 1.0) == pytest.approx(1.0 - math.exp(-1.0))
    assert polarization_fraction(3.0, 1.0) == pytest.approx(0.9502, abs=1e-4)
    assert polarization_fraction(5.0, 1.0) == pytest.approx(0.9933, abs=1e-4)
    assert polarization_fraction(1.0, 1.0, charging=False) == pytest.approx(math.exp(-1.0))


def test_terminal_voltage_and_losses() -> None:
    voltage = first_order_terminal_voltage(3.8, 2.0, 0.03, 0.038)
    assert voltage == pytest.approx(3.8 - 0.06 - 0.038)
    assert calculate_polarization_loss(0.038, 0.02) == pytest.approx(0.038**2 / 0.02)
    assert calculate_stored_energy(1000.0, 0.038) == pytest.approx(0.5 * 1000.0 * 0.038**2)


def test_invalid_inputs_rejected() -> None:
    with pytest.raises(FirstOrderRcError):
        calculate_time_constant(0.0, 1000.0)
    with pytest.raises(FirstOrderRcError):
        update_first_order_polarization(0.0, 1.0, -0.02, 1000.0, 0.1)
    with pytest.raises(FirstOrderRcError):
        polarization_fraction(-1.0, 20.0)

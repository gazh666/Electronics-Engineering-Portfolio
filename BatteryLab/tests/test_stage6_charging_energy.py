"""第六阶段能量：ZOH 主口径、梯形交叉校核、反向电量与效率。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.charging_energy import (
    calculate_charging_energy,
    integrate_trapezoid,
    integrate_zoh,
)


def test_integrators_agree_on_constant_signal():
    time = np.linspace(0.0, 1.0, 101)
    values = np.full(time.shape, 2.0)
    assert integrate_zoh(values, time) == pytest.approx(2.0)
    assert integrate_trapezoid(values, time) == pytest.approx(2.0)


def test_charging_energy_and_efficiency():
    time = np.linspace(0.0, 3600.0, 3601)
    pack_voltage = np.full(time.shape, 10.0)
    current = np.full(time.shape, 1.0)
    summary = calculate_charging_energy(time, pack_voltage, current, np.full(time.shape, 10.0), current)
    assert summary.net_charge_ah == pytest.approx(1.0, rel=1e-6)
    assert summary.battery_energy_wh == pytest.approx(10.0, rel=1e-6)
    assert summary.energy_efficiency_percent == pytest.approx(100.0, rel=1e-6)
    assert abs(summary.integration_gap_percent) < 1e-6


def test_reverse_charge_is_separated():
    time = np.array([0.0, 1.0, 2.0])
    current = np.array([1.0, -0.5, 1.0])
    summary = calculate_charging_energy(time, np.full(3, 10.0), current)
    assert summary.net_charge_ah == pytest.approx(0.5 / 3600.0, rel=1e-6)
    assert summary.reverse_charge_ah > 0.0


def test_energy_requires_positive_input():
    time = np.array([0.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        calculate_charging_energy(time, np.full(3, 10.0), np.full(3, 1.0), np.zeros(3), np.full(3, 0.0))


def test_integration_rejects_non_monotonic_time():
    with pytest.raises(ValueError):
        integrate_zoh(np.array([1.0, 1.0]), np.array([0.0, 0.0]))

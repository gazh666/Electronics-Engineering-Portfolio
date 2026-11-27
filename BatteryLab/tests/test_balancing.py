"""被动均衡：支路电流/功耗、启动停止规则与不一致性收敛。"""

from __future__ import annotations

import pytest

from protection.balancing import (
    BalancingError,
    PassiveBalancer,
    balance_branch_current,
    balance_branch_power,
    simulate_passive_balancing,
)
from protection.limits import load_limits
from scripts.stage5_common import cell_soc_for_voltage, make_pack


def test_branch_current_and_power():
    current = balance_branch_current(4.18, 100.0, 0.04)
    assert current == pytest.approx(4.18 / 100.04, rel=1e-12)
    assert balance_branch_power(current, 100.0, 0.04) == pytest.approx(current**2 * 100.04)


def test_rejects_negative_voltage():
    with pytest.raises(BalancingError):
        balance_branch_current(-1.0, 100.0, 0.04)


def test_plan_starts_only_above_start_conditions():
    limits = load_limits()
    balancer = PassiveBalancer(limits)
    channels = balancer.plan(("cell1", "cell2", "cell3"), (3.9, 3.95, 4.0), permitted=True)
    assert all(not channel.enabled for channel in channels)


def test_plan_selects_highest_cell_only():
    limits = load_limits()
    balancer = PassiveBalancer(limits)
    channels = balancer.plan(("cell1", "cell2", "cell3"), (4.12, 4.18, 4.20), permitted=True)
    assert [channel.enabled for channel in channels] == [False, False, True]
    assert channels[2].current_a == pytest.approx(4.20 / 100.04, rel=1e-9)


def test_plan_blocked_when_not_permitted():
    limits = load_limits()
    balancer = PassiveBalancer(limits)
    channels = balancer.plan(("cell1", "cell2", "cell3"), (4.12, 4.18, 4.20), permitted=False)
    assert all(not channel.enabled for channel in channels)


def test_resistor_power_check():
    limits = load_limits()
    balancer = PassiveBalancer(limits)
    assert balancer.check_resistor_power(0.20) is False
    assert balancer.check_resistor_power(0.30) is True


def test_convergence_on_frozen_ecm():
    limits = load_limits()
    socs = [cell_soc_for_voltage(voltage) for voltage in (4.05, 4.12, 4.18)]
    pack = make_pack(socs)
    result = simulate_passive_balancing(
        pack.cells, limits, duration_s=12 * 3600.0, step_s=20.0, permitted=True
    )
    assert result.initial_delta_v == pytest.approx(0.13, abs=0.01)
    assert result.final_delta_v < 0.02
    assert result.delta_reduction_fraction > 0.85
    assert result.energy_dissipated_wh > 0.0
    assert result.peak_resistor_power_w <= limits.balance_resistor_power_rating_w


def test_no_balancing_when_not_permitted():
    limits = load_limits()
    socs = [cell_soc_for_voltage(voltage) for voltage in (4.05, 4.12, 4.18)]
    pack = make_pack(socs)
    result = simulate_passive_balancing(
        pack.cells, limits, duration_s=3600.0, step_s=20.0, permitted=False
    )
    assert result.final_delta_v == pytest.approx(result.initial_delta_v)
    assert result.energy_dissipated_wh == 0.0

"""保护控制器：逐节比较器、包级电流、温度与均衡许可。"""

from __future__ import annotations

import pytest

from protection.limits import load_limits
from protection.protection_controller import ProtectionController, ProtectionControllerError
from protection.state_machine import FaultCode

CELL_IDS = ("cell1", "cell2", "cell3")


def _controller() -> ProtectionController:
    controller = ProtectionController.create(load_limits(), CELL_IDS)
    controller.arm(0.0)
    return controller


def _advance(
    controller: ProtectionController,
    times,
    voltages,
    current: float = 0.0,
    temperature: float = 25.0,
    valid: bool = True,
):
    snap = None
    for moment in times:
        snap = controller.update(moment, voltages, current, temperature, measurement_valid=valid)
    return snap


def test_normal_operation_allows_both_directions():
    controller = _controller()
    snap = controller.update(0.0, (3.9, 3.9, 3.9), 0.5, 25.0)
    assert snap.charge_allowed is True
    assert snap.discharge_allowed is True
    assert snap.active_faults == ()
    assert snap.pack_voltage_v == pytest.approx(11.7)
    assert snap.maximum_cell_voltage_v == pytest.approx(3.9)


def test_overvoltage_latches_after_confirmation_delay():
    controller = _controller()
    controller.update(0.0, (3.9, 3.9, 3.9), 0.0, 25.0)
    early = controller.update(0.010, (4.30, 3.9, 3.9), 0.0, 25.0)
    assert FaultCode.CELL_OVERVOLTAGE.value not in early.latched_faults
    # 50 ms 确认延时 + 1 ms 传输延时后进入锁存。
    snap = _advance(controller, (0.060, 0.075), (4.30, 3.9, 3.9))
    assert "CELL_OVERVOLTAGE" in snap.latched_faults
    assert snap.charge_allowed is False
    assert snap.discharge_allowed is True
    assert "cell1" in controller.state_machine.latched[FaultCode.CELL_OVERVOLTAGE].cell_id


def test_undervoltage_blocks_discharge():
    controller = _controller()
    controller.update(0.0, (3.9, 3.9, 3.9), 0.0, 25.0)
    snap = _advance(controller, (0.05, 0.15, 0.17), (3.9, 3.9, 2.70))
    assert "CELL_UNDERVOLTAGE" in snap.latched_faults
    assert snap.discharge_allowed is False
    assert snap.charge_allowed is True


def test_charge_and_discharge_overcurrent_directions():
    controller = _controller()
    controller.update(0.0, (3.9, 3.9, 3.9), -2.0, 25.0)
    snap = _advance(controller, (0.50, 0.52), (3.9, 3.9, 3.9), current=-2.0)
    assert "CHARGE_OVERCURRENT" in snap.latched_faults
    assert snap.charge_allowed is False
    assert snap.discharge_allowed is True

    controller = _controller()
    controller.update(0.0, (3.9, 3.9, 3.9), 5.0, 25.0)
    snap = _advance(controller, (0.20, 0.22), (3.9, 3.9, 3.9), current=5.0)
    assert "DISCHARGE_OVERCURRENT" in snap.latched_faults
    assert snap.discharge_allowed is False


def test_short_circuit_blocks_both():
    controller = _controller()
    controller.update(0.0, (3.9, 3.9, 3.9), 9.0, 25.0)
    snap = _advance(controller, (0.005, 0.007), (3.9, 3.9, 3.9), current=9.0)
    assert "SHORT_CIRCUIT" in snap.latched_faults
    assert snap.charge_fet_enabled is False
    assert snap.discharge_fet_enabled is False


def test_temperature_limits():
    controller = _controller()
    controller.update(0.0, (3.9, 3.9, 3.9), 0.0, 70.0)
    snap = _advance(controller, (2.0, 2.01), (3.9, 3.9, 3.9), temperature=70.0)
    assert "OVER_TEMPERATURE" in snap.latched_faults
    assert snap.charge_allowed is False and snap.discharge_allowed is False

    controller = _controller()
    controller.update(0.0, (3.9, 3.9, 3.9), 0.0, -5.0)
    snap = _advance(controller, (2.0, 2.01), (3.9, 3.9, 3.9), temperature=-5.0)
    assert "UNDER_TEMPERATURE_CHARGE" in snap.latched_faults
    assert snap.charge_allowed is False
    assert snap.discharge_allowed is True


def test_invalid_measurement_blocks_both_immediately():
    controller = _controller()
    snap = controller.update(0.0, (3.9, 3.9, 3.9), 0.0, 25.0, measurement_valid=False)
    assert snap.measurement_valid is False
    assert snap.charge_allowed is False and snap.discharge_allowed is False


def test_stale_measurement_is_invalid():
    controller = _controller()
    snap = controller.update(1.0, (3.9, 3.9, 3.9), 0.0, 25.0, measurement_time_s=0.0)
    assert snap.measurement_valid is False
    assert snap.charge_allowed is False


def test_balancing_blocked_while_discharging():
    controller = _controller()
    controller.update(0.0, (4.12, 4.18, 4.20), 1.0, 25.0)
    snap = controller.update(0.01, (4.12, 4.18, 4.20), 1.0, 25.0)
    assert all(not channel.enabled for channel in snap.balancing)


def test_balancing_enabled_at_rest_with_high_cell():
    controller = _controller()
    snap = controller.update(0.0, (4.12, 4.18, 4.20), 0.0, 25.0)
    enabled = [channel.cell_id for channel in snap.balancing if channel.enabled]
    assert enabled == ["cell3"]
    assert snap.balancing[2].current_a == pytest.approx(4.20 / 100.04, rel=1e-6)


def test_rejects_wrong_cell_count():
    controller = _controller()
    with pytest.raises(ProtectionControllerError):
        controller.update(0.0, (3.9, 3.9), 0.0, 25.0)


def test_rejects_duplicate_cell_ids():
    with pytest.raises(ProtectionControllerError):
        ProtectionController.create(load_limits(), ("cell1", "cell1", "cell3"))

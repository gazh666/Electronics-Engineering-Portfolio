"""故障状态机：锁存、独立许可、合法恢复与禁止自动重启。"""

from __future__ import annotations

import pytest

from protection.state_machine import (
    FaultCode,
    ProtectionState,
    ProtectionStateError,
    ProtectionStateMachine,
)


def _machine() -> ProtectionStateMachine:
    machine = ProtectionStateMachine(all_clear_hold_s=5.0)
    machine.arm(0.0)
    return machine


def test_overvoltage_blocks_charge_only():
    machine = _machine()
    machine.update(0.1, {FaultCode.CELL_OVERVOLTAGE: "cell1:4.30V"}, True)
    assert machine.state is ProtectionState.LATCHED
    assert machine.charge_allowed is False
    assert machine.discharge_allowed is True
    assert machine.latched_codes == ("CELL_OVERVOLTAGE",)


def test_undervoltage_blocks_discharge_only():
    machine = _machine()
    machine.update(0.1, {FaultCode.CELL_UNDERVOLTAGE: "cell3:2.70V"}, True)
    assert machine.charge_allowed is True
    assert machine.discharge_allowed is False


def test_short_circuit_and_measurement_invalid_block_both():
    machine = _machine()
    machine.update(0.1, {FaultCode.SHORT_CIRCUIT: "9A"}, True)
    assert machine.charge_allowed is False and machine.discharge_allowed is False

    machine = _machine()
    machine.update(0.1, {}, False)
    assert machine.charge_allowed is False and machine.discharge_allowed is False
    assert "MEASUREMENT_INVALID" in machine.latched_codes


def test_latch_survives_condition_clearing():
    machine = _machine()
    machine.update(0.1, {FaultCode.CELL_OVERVOLTAGE: "cell1"}, True)
    machine.update(0.2, {}, True)
    assert machine.latched_codes == ("CELL_OVERVOLTAGE",)
    assert machine.charge_allowed is False


def test_recovery_rejected_before_hold_window():
    machine = _machine()
    machine.update(0.1, {FaultCode.CELL_OVERVOLTAGE: "cell1"}, True)
    machine.update(0.2, {}, True)
    assert machine.request_recovery(3.0) is False
    assert machine.latched_codes == ("CELL_OVERVOLTAGE",)


def test_recovery_after_hold_requires_rearm():
    machine = _machine()
    machine.update(0.1, {FaultCode.CELL_OVERVOLTAGE: "cell1"}, True)
    machine.update(0.2, {}, True)
    assert machine.request_recovery(5.3) is True
    assert machine.latched_codes == ()
    assert machine.charge_allowed is False  # 恢复后仍需重新使能
    assert machine.discharge_allowed is False
    machine.arm(5.4)
    assert machine.charge_allowed is True and machine.discharge_allowed is True


def test_recovery_rejected_while_fault_active():
    machine = _machine()
    machine.update(0.1, {FaultCode.CELL_OVERVOLTAGE: "cell1"}, True)
    machine.update(6.0, {FaultCode.CELL_OVERVOLTAGE: "cell1"}, True)
    assert machine.request_recovery(6.0) is False


def test_no_permission_without_arming():
    machine = ProtectionStateMachine(all_clear_hold_s=5.0)
    machine.update(0.0, {}, True)
    assert machine.charge_allowed is False
    assert machine.discharge_allowed is False


def test_arm_rejected_when_latched():
    machine = _machine()
    machine.update(0.1, {FaultCode.OVER_TEMPERATURE: "70C"}, True)
    with pytest.raises(ProtectionStateError):
        machine.arm(0.2)


def test_event_log_records_latch_and_recovery():
    machine = _machine()
    machine.update(0.1, {FaultCode.CELL_OVERVOLTAGE: "cell1"}, True)
    machine.update(0.2, {}, True)
    machine.request_recovery(5.3)
    names = [event["event"] for event in machine.events]
    assert "fault_latched" in names
    assert "recovered" in names
    assert machine.snapshot()["recovery_count"] == 1

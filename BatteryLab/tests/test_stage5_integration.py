"""第五阶段集成测试：保护判决 → 充放电许可 → 真实开关阻断。"""

from __future__ import annotations

import pytest

from circuits.protection_mosfet import run_switch_case_matrix
from protection.limits import load_limits
from protection.protection_controller import ProtectionController


def _controller() -> ProtectionController:
    controller = ProtectionController.create(load_limits(), ("cell1", "cell2", "cell3"))
    controller.arm(0.0)
    return controller


def test_overvoltage_sequence_end_to_end():
    controller = _controller()
    controller.update(0.0, (3.95, 3.96, 3.94), 0.0, 25.0)
    for step in range(1, 9):
        snap = controller.update(step * 0.01, (4.30, 3.96, 3.94), 0.0, 25.0)
    assert snap.charge_allowed is False
    assert snap.discharge_allowed is True

    # 故障消失，比较器释放需要同样的确认延时，再保持 5 s 后才允许恢复。
    controller.update(0.2, (4.10, 3.96, 3.94), 0.0, 25.0)
    controller.update(0.3, (4.10, 3.96, 3.94), 0.0, 25.0)
    cleared = controller.update(0.4, (4.10, 3.96, 3.94), 0.0, 25.0)
    assert cleared.latched_faults == ("CELL_OVERVOLTAGE",)
    assert controller.request_recovery(5.5) is True
    recovered = controller.update(5.51, (4.10, 3.96, 3.94), 0.0, 25.0)
    assert recovered.charge_allowed is False
    controller.arm(5.52)
    armed = controller.update(5.53, (4.10, 3.96, 3.94), 0.0, 25.0)
    assert armed.charge_allowed is True and armed.discharge_allowed is True


def test_limits_respect_stage4_measurement_domain():
    limits = load_limits()
    assert limits.cell_overvoltage_trip_v <= limits.afe_measurement_max_v
    assert limits.cell_undervoltage_trip_v >= limits.afe_measurement_min_v


def test_permission_maps_to_real_blocking():
    limits = load_limits()
    cases = {case.case: case for case in run_switch_case_matrix(limits)}
    # 充电许可为 False 时，对应工况的真实充电电流必须被阻断。
    assert abs(cases["CASE_C_CHG_OFF_BLOCK_CHARGE"].charge_current_a) < 1e-3
    # 放电许可为 False 时，负载电流必须被阻断。
    assert abs(cases["CASE_D_DSG_OFF_BLOCK_DISCHARGE"].load_current_a) < 1e-3


def test_measurement_invalid_disables_both_fets():
    controller = _controller()
    snap = controller.update(0.0, (3.9, 3.9, 3.9), 0.0, 25.0, measurement_valid=False)
    assert snap.charge_fet_enabled is False
    assert snap.discharge_fet_enabled is False



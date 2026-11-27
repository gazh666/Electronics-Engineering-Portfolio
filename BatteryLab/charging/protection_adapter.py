"""BMS 保护适配：把第五阶段真实保护结果转换为充电器许可状态。

不复制第五阶段状态机，也不另建永远返回 allowed=True 的假接口。
控制优先级：BMS 独立保护 > 充电终止逻辑 > CC-CV 控制 > PWM 指令。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from protection.limits import ProtectionLimits, load_limits
from protection.protection_controller import (
    ProtectionController,
    ProtectionSnapshot,
)


@dataclass(frozen=True)
class ChargePermission:
    allowed: bool
    measurement_valid: bool
    active_faults: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "measurement_valid": self.measurement_valid,
            "active_faults": list(self.active_faults),
            "reason": self.reason,
        }


def evaluate_charge_permission(
    charge_allowed: bool,
    measurement_valid: bool,
    active_faults: Sequence[str],
) -> ChargePermission:
    allowed = bool(charge_allowed) and bool(measurement_valid)
    if not measurement_valid:
        reason = "INVALID_MEASUREMENT"
    elif not charge_allowed:
        reason = "BMS_CHARGE_INHIBITED"
    else:
        reason = "ALLOWED"
    return ChargePermission(
        allowed=allowed,
        measurement_valid=bool(measurement_valid),
        active_faults=tuple(str(fault) for fault in active_faults),
        reason=reason,
    )


def permission_from_snapshot(snapshot: ProtectionSnapshot) -> ChargePermission:
    return evaluate_charge_permission(
        charge_allowed=snapshot.charge_allowed,
        measurement_valid=snapshot.measurement_valid,
        active_faults=snapshot.latched_faults or snapshot.active_faults,
    )


def create_protection_controller(
    cell_ids: Sequence[str] = ("cell1", "cell2", "cell3"),
    limits: ProtectionLimits | None = None,
) -> ProtectionController:
    """构造第五阶段真实保护控制器（充电器只读使用其结果）。"""
    active_limits = limits or load_limits()
    controller = ProtectionController.create(active_limits, list(cell_ids))
    controller.arm(0.0)
    return controller

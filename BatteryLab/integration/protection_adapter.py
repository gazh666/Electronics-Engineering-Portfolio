"""保护适配：把第五阶段真实保护控制器包装成系统许可接口。

保护阈值来自 ``configs/protection_config.yaml``，属于第五阶段工程设计的
教学阈值，不是 BQ76922 出厂 OTP 或寄存器配置。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from integration.battery_port_adapter import BatteryPort, TerminalState
from protection.limits import ProtectionLimits, load_limits
from protection.protection_controller import ProtectionController, ProtectionSnapshot


@dataclass(frozen=True)
class ProtectionPermission:
    time_s: float
    charge_allowed: bool
    discharge_allowed: bool
    state: str
    active_faults: tuple[str, ...]
    latched_faults: tuple[str, ...]
    minimum_cell_voltage_v: float
    pack_current_a: float
    measurement_valid: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_s": self.time_s,
            "charge_allowed": self.charge_allowed,
            "discharge_allowed": self.discharge_allowed,
            "state": self.state,
            "active_faults": list(self.active_faults),
            "latched_faults": list(self.latched_faults),
            "minimum_cell_voltage_v": self.minimum_cell_voltage_v,
            "pack_current_a": self.pack_current_a,
            "measurement_valid": self.measurement_valid,
        }


class ProtectionGate:
    """带锁存的独立 BMS 许可，优先于转换器控制。"""

    def __init__(self, controller: ProtectionController, limits: ProtectionLimits) -> None:
        self.controller = controller
        self.limits = limits
        self.last_snapshot: ProtectionSnapshot | None = None

    @classmethod
    def from_stage5_config(
        cls,
        cell_ids: Sequence[str],
        *,
        limits: ProtectionLimits | None = None,
        controller: ProtectionController | None = None,
    ) -> "ProtectionGate":
        resolved = limits or load_limits()
        instance = controller or ProtectionController.create(resolved, cell_ids)
        return cls(instance, resolved)

    def arm(self, time_s: float = 0.0) -> None:
        self.controller.arm(time_s)

    def update(
        self,
        time_s: float,
        terminal: TerminalState,
        current_a: float,
        temperature_c: float = 25.0,
        *,
        measurement_valid: bool = True,
        measurement_time_s: float | None = None,
    ) -> ProtectionPermission:
        snapshot = self.controller.update(
            time_s=time_s,
            cell_voltages_v=terminal.cell_voltages_v,
            pack_current_a=current_a,
            temperature_c=temperature_c,
            measurement_valid=measurement_valid,
            measurement_time_s=measurement_time_s,
        )
        self.last_snapshot = snapshot
        return self._permission(snapshot)

    def get_permission(self) -> ProtectionPermission:
        if self.last_snapshot is None:
            raise RuntimeError("ProtectionGate 尚未执行首次 update")
        return self._permission(self.last_snapshot)

    def request_recovery(self, time_s: float) -> bool:
        accepted = self.controller.request_recovery(time_s)
        return bool(accepted)

    @staticmethod
    def _permission(snapshot: ProtectionSnapshot) -> ProtectionPermission:
        return ProtectionPermission(
            time_s=snapshot.time_s,
            charge_allowed=snapshot.charge_allowed,
            discharge_allowed=snapshot.discharge_allowed,
            state=snapshot.state.value,
            active_faults=snapshot.active_faults,
            latched_faults=snapshot.latched_faults,
            minimum_cell_voltage_v=snapshot.minimum_cell_voltage_v,
            pack_current_a=snapshot.pack_current_a,
            measurement_valid=snapshot.measurement_valid,
        )


def evaluate_port_permission(
    gate: ProtectionGate,
    port: BatteryPort,
    current_a: float,
    time_s: float,
    *,
    temperature_c: float = 25.0,
) -> ProtectionPermission:
    terminal = port.calculate_terminal_state(current_a)
    return gate.update(time_s, terminal, current_a, temperature_c)


__all__ = ["ProtectionGate", "ProtectionPermission", "evaluate_port_permission"]

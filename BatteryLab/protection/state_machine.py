"""保护故障状态机：独立充放电许可、故障锁存、合法恢复。

与第五阶段之前的状态机不同，这里把"故障是否仍然存在"和"故障是否曾被锁存"
分开保存。锁存后即使测量恢复正常，也不允许自动重新充电或放电；必须满足
全部条件清零并保持一段时间，再由外部显式请求恢复和重新使能。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FaultCode(str, Enum):
    """全部可锁存故障码。"""

    CELL_OVERVOLTAGE = "CELL_OVERVOLTAGE"
    CELL_UNDERVOLTAGE = "CELL_UNDERVOLTAGE"
    CHARGE_OVERCURRENT = "CHARGE_OVERCURRENT"
    DISCHARGE_OVERCURRENT = "DISCHARGE_OVERCURRENT"
    SHORT_CIRCUIT = "SHORT_CIRCUIT"
    OVER_TEMPERATURE = "OVER_TEMPERATURE"
    UNDER_TEMPERATURE_CHARGE = "UNDER_TEMPERATURE_CHARGE"
    CHARGE_HIGH_TEMPERATURE = "CHARGE_HIGH_TEMPERATURE"
    MEASUREMENT_INVALID = "MEASUREMENT_INVALID"
    BALANCE_OVERTEMPERATURE = "BALANCE_OVERTEMPERATURE"


class ProtectionState(str, Enum):
    NORMAL = "NORMAL"
    LATCHED = "LATCHED"


# 哪些故障禁止充电、哪些禁止放电。短路与测量失效同时禁止两个方向。
CHARGE_INHIBIT = frozenset(
    {
        FaultCode.CELL_OVERVOLTAGE,
        FaultCode.CHARGE_OVERCURRENT,
        FaultCode.SHORT_CIRCUIT,
        FaultCode.OVER_TEMPERATURE,
        FaultCode.UNDER_TEMPERATURE_CHARGE,
        FaultCode.CHARGE_HIGH_TEMPERATURE,
        FaultCode.MEASUREMENT_INVALID,
    }
)
DISCHARGE_INHIBIT = frozenset(
    {
        FaultCode.CELL_UNDERVOLTAGE,
        FaultCode.DISCHARGE_OVERCURRENT,
        FaultCode.SHORT_CIRCUIT,
        FaultCode.OVER_TEMPERATURE,
        FaultCode.MEASUREMENT_INVALID,
    }
)


class ProtectionStateError(ValueError):
    """状态机输入非法。"""


@dataclass(frozen=True)
class FaultRecord:
    code: FaultCode
    first_trip_time_s: float
    last_seen_time_s: float
    cell_id: str
    trip_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "first_trip_time_s": self.first_trip_time_s,
            "last_seen_time_s": self.last_seen_time_s,
            "cell_id": self.cell_id,
            "trip_count": self.trip_count,
        }


@dataclass
class ProtectionStateMachine:
    """锁存型保护状态机。"""

    all_clear_hold_s: float = 5.0
    require_measurement_valid: bool = True

    state: ProtectionState = ProtectionState.NORMAL
    armed: bool = False
    recovery_requested: bool = False
    latched: dict[FaultCode, FaultRecord] = field(default_factory=dict)
    active_conditions: dict[FaultCode, str] = field(default_factory=dict)
    all_clear_since_s: float | None = None
    last_update_s: float | None = None
    recovery_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not math.isfinite(self.all_clear_hold_s) or self.all_clear_hold_s <= 0.0:
            raise ProtectionStateError("全部清零保持时间必须为正")
        self._log(0.0, "state_machine_init", {"all_clear_hold_s": self.all_clear_hold_s})

    def _log(self, time_s: float, event: str, payload: Mapping[str, Any] | None = None) -> None:
        record = {"time_s": float(time_s), "event": event}
        if payload:
            record.update(dict(payload))
        self.events.append(record)

    def arm(self, time_s: float = 0.0) -> None:
        """显式使能。锁存状态下不允许使能。"""
        if self.latched:
            raise ProtectionStateError("存在锁存故障，必须先合法恢复")
        self.armed = True
        self._log(time_s, "armed")

    def disarm(self, time_s: float = 0.0, reason: str = "external") -> None:
        self.armed = False
        self._log(time_s, "disarmed", {"reason": reason})

    def update(
        self,
        time_s: float,
        active: Mapping[FaultCode, str | None],
        measurement_valid: bool,
    ) -> ProtectionState:
        """更新故障锁存状态。

        ``active`` 中键为故障码，值为附加说明（例如 cell1）；值为 ``None`` 表示该
        故障当前不存在。未出现在映射中的故障视为不存在。
        """
        now = float(time_s)
        if not math.isfinite(now):
            raise ProtectionStateError("时间必须是有限数值")
        if self.last_update_s is not None and now < self.last_update_s:
            raise ProtectionStateError("时间不能倒退")
        self.last_update_s = now

        current: dict[FaultCode, str] = {
            code: str(note) for code, note in active.items() if note is not None
        }
        if self.require_measurement_valid and not measurement_valid:
            current[FaultCode.MEASUREMENT_INVALID] = "measurement_invalid"
        self.active_conditions = current

        for code, note in current.items():
            existing = self.latched.get(code)
            if existing is None:
                self.latched[code] = FaultRecord(
                    code=code, first_trip_time_s=now, last_seen_time_s=now, cell_id=note
                )
                self._log(now, "fault_latched", {"code": code.value, "note": note})
            else:
                self.latched[code] = FaultRecord(
                    code=code,
                    first_trip_time_s=existing.first_trip_time_s,
                    last_seen_time_s=now,
                    cell_id=note,
                    trip_count=existing.trip_count + 1,
                )

        if current:
            self.state = ProtectionState.LATCHED
            self.all_clear_since_s = None
        else:
            if self.latched:
                self.state = ProtectionState.LATCHED
                if self.all_clear_since_s is None:
                    self.all_clear_since_s = now
                    self._log(now, "all_clear_window_started")
            else:
                self.state = ProtectionState.NORMAL
                self.all_clear_since_s = None

        return self.state

    def request_recovery(self, time_s: float) -> bool:
        """请求清除锁存。只有满足全部条件才返回 True。"""
        now = float(time_s)
        self.recovery_requested = True
        if not self.latched:
            self.recovery_requested = False
            return True
        if self.active_conditions:
            self._log(now, "recovery_rejected", {"reason": "active_faults"})
            return False
        if self.require_measurement_valid and FaultCode.MEASUREMENT_INVALID in self.latched:
            # 测量失效时无法证明故障已消失。
            self._log(now, "recovery_rejected", {"reason": "measurement_invalid_latched"})
            return False
        if self.all_clear_since_s is None:
            self._log(now, "recovery_rejected", {"reason": "no_clear_window"})
            return False
        if now - self.all_clear_since_s < self.all_clear_hold_s:
            self._log(
                now,
                "recovery_rejected",
                {"reason": "clear_window_too_short", "elapsed_s": now - self.all_clear_since_s},
            )
            return False

        cleared = sorted(code.value for code in self.latched)
        self.latched.clear()
        self.state = ProtectionState.NORMAL
        self.all_clear_since_s = None
        self.recovery_requested = False
        self.armed = False  # 恢复后仍需显式重新使能，禁止隐式自动重启
        self.recovery_count += 1
        self._log(now, "recovered", {"cleared": cleared, "requires_rearm": True})
        return True

    @property
    def latched_codes(self) -> tuple[str, ...]:
        return tuple(sorted(code.value for code in self.latched))

    @property
    def charge_allowed(self) -> bool:
        if not self.armed:
            return False
        if FaultCode.MEASUREMENT_INVALID in self.active_conditions:
            return False
        return not any(code in CHARGE_INHIBIT for code in self.latched)

    @property
    def discharge_allowed(self) -> bool:
        if not self.armed:
            return False
        if FaultCode.MEASUREMENT_INVALID in self.active_conditions:
            return False
        return not any(code in DISCHARGE_INHIBIT for code in self.latched)

    @property
    def balancing_allowed(self) -> bool:
        # 均衡只在正常、已使能且允许充电或静置时进行。
        if not self.armed or self.latched:
            return False
        if FaultCode.MEASUREMENT_INVALID in self.active_conditions:
            return False
        if FaultCode.BALANCE_OVERTEMPERATURE in self.active_conditions:
            return False
        return self.charge_allowed or self.state == ProtectionState.NORMAL

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "armed": self.armed,
            "charge_allowed": self.charge_allowed,
            "discharge_allowed": self.discharge_allowed,
            "balancing_allowed": self.balancing_allowed,
            "latched": [record.to_dict() for record in self.latched.values()],
            "active_conditions": {code.value: note for code, note in self.active_conditions.items()},
            "all_clear_since_s": self.all_clear_since_s,
            "recovery_count": self.recovery_count,
            "event_count": len(self.events),
        }

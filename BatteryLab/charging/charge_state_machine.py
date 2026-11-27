"""充电会话状态机：IDLE → SOFT_START → CC → CV → COMPLETE / FAULT / TIMEOUT。

COMPLETE 与 FAULT 都是终止状态，不能自动恢复充电；必须显式新建会话。
控制区域标签不等于真实恒流/恒压，最终状态还需要结合电压容差与实际电流判定。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from charging.charge_termination import TerminationTracker


class ChargeState(str, Enum):
    IDLE = "IDLE"
    SOFT_START = "SOFT_START"
    CC = "CC"
    CV = "CV"
    COMPLETE = "COMPLETE"
    FAULT = "FAULT"
    TIMEOUT = "TIMEOUT"


TERMINAL_STATES = frozenset(
    {ChargeState.IDLE, ChargeState.COMPLETE, ChargeState.FAULT, ChargeState.TIMEOUT}
)
ACTIVE_STATES = frozenset({ChargeState.SOFT_START, ChargeState.CC, ChargeState.CV})


@dataclass
class ChargeSession:
    termination_current_a: float = 0.1
    termination_hold_s: float = 60.0
    maximum_charge_time_s: float = 14400.0
    voltage_target_v: float = 12.15
    cv_voltage_tolerance_v: float = 0.02
    minimum_start_voltage_v: float = 6.0
    measurement_max_age_s: float = 0.05

    state: ChargeState = ChargeState.IDLE
    start_time_s: float | None = None
    last_time_s: float | None = None
    fault_reason: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    termination: TerminationTracker = field(init=False)

    def __post_init__(self) -> None:
        self.termination = TerminationTracker(
            current_limit_a=self.termination_current_a,
            hold_time_s=self.termination_hold_s,
        )
        for name in (
            "termination_current_a",
            "termination_hold_s",
            "maximum_charge_time_s",
            "voltage_target_v",
            "cv_voltage_tolerance_v",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"Invalid {name}")

    def _log(self, time_s: float, event: str, **payload: Any) -> None:
        record = {"time_s": float(time_s), "event": event}
        record.update(payload)
        self.events.append(record)

    def start(
        self,
        time_s: float,
        bms_charge_allowed: bool,
        pack_voltage_v: float | None = None,
    ) -> ChargeState:
        if not math.isfinite(time_s):
            raise ValueError("Invalid time")
        if self.state is not ChargeState.IDLE:
            raise RuntimeError("Session not idle")
        if not bms_charge_allowed:
            raise RuntimeError("BMS denies charging")
        if pack_voltage_v is not None:
            if not math.isfinite(pack_voltage_v):
                raise ValueError("Invalid pack voltage")
            if pack_voltage_v < self.minimum_start_voltage_v:
                raise RuntimeError("Pack voltage below start inhibit threshold")
        self.start_time_s = float(time_s)
        self.last_time_s = float(time_s)
        self.termination.reset()
        self.state = ChargeState.SOFT_START
        self._log(time_s, "SESSION_START")
        return self.state

    def update(
        self,
        time_s: float,
        pack_voltage_v: float,
        charging_current_a: float,
        control_region: str,
        bms_charge_allowed: bool,
        measurement_valid: bool,
        input_available: bool,
        charge_path_confirmed: bool,
        measurement_age_s: float | None = None,
    ) -> ChargeState:
        if self.state in TERMINAL_STATES:
            return self.state

        values = [time_s, pack_voltage_v, charging_current_a]
        if not all(math.isfinite(v) for v in values):
            return self._fault(time_s, "NON_FINITE_MEASUREMENT")

        if self.last_time_s is not None and time_s < self.last_time_s:
            raise ValueError("Time reversed")
        self.last_time_s = float(time_s)

        if measurement_age_s is not None:
            if not math.isfinite(measurement_age_s) or measurement_age_s > self.measurement_max_age_s:
                measurement_valid = False

        if not (bms_charge_allowed and measurement_valid and input_available and charge_path_confirmed):
            if not bms_charge_allowed:
                return self._fault(time_s, "BMS_CHARGE_INHIBITED")
            if not measurement_valid:
                return self._fault(time_s, "INVALID_MEASUREMENT")
            if not input_available:
                return self._fault(time_s, "INPUT_UNAVAILABLE")
            return self._fault(time_s, "CHARGE_PATH_OPEN")

        if charging_current_a < 0.0:
            return self._fault(time_s, "REVERSE_CURRENT")

        if self.start_time_s is None:
            raise RuntimeError("Session not started")
        elapsed = float(time_s) - self.start_time_s
        if elapsed >= self.maximum_charge_time_s:
            self.state = ChargeState.TIMEOUT
            self._log(time_s, "TIMEOUT", elapsed_s=elapsed)
            return self.state

        near_cv_voltage = (
            abs(pack_voltage_v - self.voltage_target_v) <= self.cv_voltage_tolerance_v
        )

        if control_region == "SOFT_START":
            next_state = ChargeState.SOFT_START
        elif control_region == "VOLTAGE_REGULATION" and near_cv_voltage:
            next_state = ChargeState.CV
        else:
            next_state = ChargeState.CC

        if next_state is not self.state:
            self._log(time_s, "STATE_CHANGE", from_state=self.state.value, to_state=next_state.value)
        self.state = next_state

        termination_condition = (
            self.state is ChargeState.CV
            and near_cv_voltage
            and 0.0 <= charging_current_a <= self.termination_current_a
        )
        if self.termination.update(time_s, charging_current_a, near_cv_voltage) and termination_condition:
            self.state = ChargeState.COMPLETE
            self._log(
                time_s,
                "COMPLETE",
                held_s=self.termination.held_time_s,
                current_a=charging_current_a,
            )
        return self.state

    def _fault(self, time_s: float, reason: str) -> ChargeState:
        self.fault_reason = reason
        self.termination.reset()
        if self.state is not ChargeState.FAULT:
            self._log(time_s, "FAULT", reason=reason)
        self.state = ChargeState.FAULT
        return self.state

    @property
    def charge_enabled(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def elapsed_s(self) -> float:
        if self.start_time_s is None or self.last_time_s is None:
            return 0.0
        return float(self.last_time_s - self.start_time_s)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "charge_enabled": self.charge_enabled,
            "start_time_s": self.start_time_s,
            "last_time_s": self.last_time_s,
            "elapsed_s": self.elapsed_s,
            "fault_reason": self.fault_reason,
            "termination_held_s": self.termination.held_time_s,
            "events": list(self.events),
        }

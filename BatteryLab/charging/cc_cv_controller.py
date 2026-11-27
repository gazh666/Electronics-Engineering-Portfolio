"""CC-CV 级联控制器：电压外环产生电流指令，电流内环产生占空比。

电流内环使用电感电流反馈；稳态时电感平均电流与电池充电电流近似一致，
但动态过程中输出电容电流不可忽略，因此充电性能与终止判定必须读取实际电池电流。

``control_region`` 只表示控制指令区域，不等于实际已经达到恒流或恒压。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from charging.pi_controller import PIController
from charging.soft_start import CurrentSoftStart


@dataclass(frozen=True)
class ChargerFeedback:
    vin_v: float
    pack_voltage_v: float
    output_voltage_v: float
    inductor_current_a: float
    charging_current_a: float
    bms_charge_allowed: bool
    measurement_valid: bool
    input_available: bool
    measurement_age_s: float = 0.0
    charge_path_confirmed: bool = True


@dataclass(frozen=True)
class ChargerCommand:
    duty: float
    current_reference_a: float
    control_region: str
    enabled: bool
    voltage_error_v: float = 0.0
    current_error_a: float = 0.0
    disable_reason: str = ""


@dataclass
class CCCVController:
    voltage_pi: PIController
    current_pi: PIController
    soft_start: CurrentSoftStart
    voltage_target_v: float = 12.15
    current_target_a: float = 1.0
    duty_max: float = 0.9
    duty_min: float = 0.0
    diode_drop_v: float = 0.5
    minimum_pack_voltage_v: float = 6.0
    measurement_max_age_s: float = 0.05

    def __post_init__(self) -> None:
        for name in ("voltage_target_v", "current_target_a", "duty_max", "diode_drop_v"):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"Invalid {name}")
        if self.current_target_a <= 0 or self.duty_max <= 0:
            raise ValueError("Invalid target or duty limit")
        if not 0.0 <= self.duty_min < self.duty_max < 1.0:
            raise ValueError("Invalid duty range")

    def reset(self) -> None:
        self.voltage_pi.reset()
        self.current_pi.reset()
        self.soft_start.reset()

    def disabled_command(self, reason: str, voltage_error_v: float = 0.0) -> ChargerCommand:
        self.reset()
        return ChargerCommand(
            duty=0.0,
            current_reference_a=0.0,
            control_region="DISABLED",
            enabled=False,
            voltage_error_v=voltage_error_v,
            disable_reason=reason,
        )

    def _guard_reason(self, feedback: ChargerFeedback) -> str | None:
        if not feedback.bms_charge_allowed:
            return "BMS_CHARGE_INHIBITED"
        if not feedback.measurement_valid:
            return "INVALID_MEASUREMENT"
        if feedback.measurement_age_s > self.measurement_max_age_s:
            return "STALE_MEASUREMENT"
        if not feedback.input_available or feedback.vin_v <= 0.0:
            return "INPUT_UNAVAILABLE"
        if not feedback.charge_path_confirmed:
            return "CHARGE_PATH_OPEN"
        if feedback.pack_voltage_v < self.minimum_pack_voltage_v:
            return "PACK_UNDERVOLTAGE_INHIBIT"
        return None

    def step(self, feedback: ChargerFeedback, dt_s: float) -> ChargerCommand:
        values = [
            feedback.vin_v,
            feedback.pack_voltage_v,
            feedback.output_voltage_v,
            feedback.inductor_current_a,
            feedback.charging_current_a,
            dt_s,
        ]
        if not all(math.isfinite(v) for v in values):
            return self.disabled_command("NON_FINITE_INPUT")
        if dt_s <= 0:
            raise ValueError("Invalid controller period")

        voltage_error = self.voltage_target_v - feedback.pack_voltage_v
        reason = self._guard_reason(feedback)
        if reason is not None:
            return self.disabled_command(reason, voltage_error)

        current_limit = self.soft_start.step(self.current_target_a, dt_s)

        current_reference = self.voltage_pi.step(
            error=voltage_error,
            dt_s=dt_s,
            lower=0.0,
            upper=current_limit,
        )

        current_error = current_reference - feedback.inductor_current_a

        duty_feedforward = (feedback.output_voltage_v + self.diode_drop_v) / (
            feedback.vin_v + self.diode_drop_v
        )
        duty_feedforward = min(max(duty_feedforward, self.duty_min), self.duty_max)

        duty = self.current_pi.step(
            error=current_error,
            dt_s=dt_s,
            lower=self.duty_min,
            upper=self.duty_max,
            feedforward=duty_feedforward,
        )

        if current_limit < self.current_target_a - 1e-9:
            region = "SOFT_START"
        elif current_reference >= current_limit - 1e-9:
            region = "CURRENT_LIMIT"
        else:
            region = "VOLTAGE_REGULATION"

        return ChargerCommand(
            duty=duty,
            current_reference_a=current_reference,
            control_region=region,
            enabled=True,
            voltage_error_v=voltage_error,
            current_error_a=current_error,
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "voltage_loop": self.voltage_pi.diagnostics(),
            "current_loop": self.current_pi.diagnostics(),
            "soft_start_fraction": self.soft_start.fraction,
            "voltage_target_v": self.voltage_target_v,
            "current_target_a": self.current_target_a,
        }

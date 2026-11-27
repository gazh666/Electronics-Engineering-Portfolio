"""可复用 PI 控制器：限幅、前馈、条件积分与反计算抗饱和。

控制律与 ``circuits.charger_spice_controller`` 网表中的行为源一致：

1. ``u_raw = feedforward + Kp*e + x_integral``
2. ``u = clamp(u_raw, lower, upper)``
3. 冻结判据：饱和方向与误差方向相同 → 积分输入为 0；
   否则 ``dx/dt = Ki*e + Kaw*(u - u_raw)``。

为什么不用纯反计算：恒流段电压环长期饱和时，反计算项会把电流指令
稳定拉低 ``(Ki/Kaw)*e``，造成持续恒流误差，而这是控制器缺陷不是电池特性。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from charging.anti_windup import clamp, conditional_integral_rate, is_frozen


@dataclass
class PIController:
    kp: float
    ki: float
    kaw: float = 0.0
    integral: float = 0.0
    last_error: float = 0.0
    last_raw: float = 0.0
    last_output: float = 0.0
    last_correction: float = 0.0
    steps: int = 0
    saturation_steps: int = 0
    max_abs_integral: float = 0.0
    reset_count: int = 0
    history: list[dict[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        values = [self.kp, self.ki, self.kaw, self.integral]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Invalid PI parameter")
        if min(self.kp, self.ki, self.kaw) < 0:
            raise ValueError("Negative gain")
        if self.ki <= 0:
            raise ValueError("Ki must be positive")

    def reset(self, integral: float = 0.0) -> None:
        if not math.isfinite(integral):
            raise ValueError("Invalid integral state")
        self.integral = float(integral)
        self.last_error = 0.0
        self.last_raw = 0.0
        self.last_output = 0.0
        self.last_correction = 0.0
        self.reset_count += 1

    def step(
        self,
        error: float,
        dt_s: float,
        lower: float,
        upper: float,
        feedforward: float = 0.0,
        record: bool = False,
    ) -> float:
        values = [error, dt_s, lower, upper, feedforward]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Invalid controller input")
        if dt_s <= 0:
            raise ValueError("Invalid control period")

        unsaturated = feedforward + self.kp * error + self.integral
        saturated = clamp(unsaturated, lower, upper)
        rate = conditional_integral_rate(
            self.ki, error, self.kaw, saturated, unsaturated
        )
        self.integral += rate * dt_s
        if not math.isfinite(self.integral):
            raise RuntimeError("PI integral overflow")

        correction = rate - self.ki * error
        self.last_error = float(error)
        self.last_raw = float(unsaturated)
        self.last_output = float(saturated)
        self.last_correction = float(correction)
        self.steps += 1
        if abs(unsaturated - saturated) > 1e-12:
            self.saturation_steps += 1
        self.max_abs_integral = max(self.max_abs_integral, abs(self.integral))
        if record:
            self.history.append(
                {
                    "step": float(self.steps),
                    "error": self.last_error,
                    "raw": self.last_raw,
                    "output": self.last_output,
                    "integral": self.integral,
                    "anti_windup_correction": self.last_correction,
                }
            )
        return saturated

    @property
    def saturated(self) -> bool:
        return abs(self.last_raw - self.last_output) > 1e-12

    def diagnostics(self) -> dict[str, float]:
        return {
            "steps": float(self.steps),
            "saturation_steps": float(self.saturation_steps),
            "saturation_fraction": self.saturation_steps / self.steps if self.steps else 0.0,
            "integral": float(self.integral),
            "max_abs_integral": float(self.max_abs_integral),
            "last_output": float(self.last_output),
            "last_raw": float(self.last_raw),
            "last_correction": float(self.last_correction),
        }

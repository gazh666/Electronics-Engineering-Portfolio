"""充电终止判定：低电流必须持续保持时间，短暂低电流不得误判完成。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class TerminationTracker:
    current_limit_a: float = 0.1
    hold_time_s: float = 60.0
    current_tolerance_a: float = 0.0
    since_s: float | None = None
    last_time_s: float | None = None

    def __post_init__(self) -> None:
        for name in ("current_limit_a", "hold_time_s", "current_tolerance_a"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"Invalid {name}")
        if self.hold_time_s <= 0.0:
            raise ValueError("hold_time_s must be positive")

    def reset(self) -> None:
        self.since_s = None
        self.last_time_s = None

    def update(self, time_s: float, current_a: float, voltage_near_target: bool) -> bool:
        """返回 True 表示终止保持时间已满足。"""
        if not all(math.isfinite(v) for v in (time_s, current_a)):
            raise ValueError("Invalid termination input")
        self.last_time_s = float(time_s)
        satisfied = (
            voltage_near_target
            and 0.0 <= current_a <= self.current_limit_a + self.current_tolerance_a
        )
        if not satisfied:
            self.since_s = None
            return False
        if self.since_s is None:
            self.since_s = float(time_s)
            return False
        return (float(time_s) - self.since_s) >= self.hold_time_s

    @property
    def held_time_s(self) -> float:
        if self.since_s is None or self.last_time_s is None:
            return 0.0
        return max(0.0, self.last_time_s - self.since_s)

    @property
    def termination_active(self) -> bool:
        return self.since_s is not None

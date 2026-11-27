"""充电电流软启动：把电流参考按线性斜坡抬到目标值。

软启动设定时间不等于实际恒流建立时间；后者必须由真实波形测量。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class CurrentSoftStart:
    duration_s: float
    elapsed_s: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.duration_s):
            raise ValueError("Invalid soft-start duration")
        if self.duration_s < 0:
            raise ValueError("Invalid duration")

    def reset(self) -> None:
        self.elapsed_s = 0.0

    @property
    def fraction(self) -> float:
        if self.duration_s == 0.0:
            return 1.0
        return min(self.elapsed_s / self.duration_s, 1.0)

    @property
    def complete(self) -> bool:
        return self.fraction >= 1.0

    def step(self, target_current_a: float, dt_s: float) -> float:
        if not all(math.isfinite(v) for v in [self.duration_s, target_current_a, dt_s]):
            raise ValueError("Invalid soft-start data")
        if self.duration_s < 0:
            raise ValueError("Invalid duration")
        if target_current_a < 0 or dt_s <= 0:
            raise ValueError("Invalid input")
        if self.duration_s == 0:
            return target_current_a
        self.elapsed_s += dt_s
        return target_current_a * min(self.elapsed_s / self.duration_s, 1.0)

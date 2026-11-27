"""安时积分（库仑计数）SOC 估计。

公式（放电为正、充电为负）：

``SOC_next = SOC - I_eff * dt / (3600 * Q)``

放电时 ``I_eff = I / eta_discharge``，充电时 ``I_eff = I * eta_charge``，
与第二阶段 ``battery_models.states.update_soc`` 的方向约定一致。

注意：本模块的 0-1 限幅是**估计器状态限幅**，不是物理电池状态更新；
每次限幅都会记录原始未限幅结果，禁止用裁剪隐藏累计积分误差。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SECONDS_PER_HOUR = 3600.0


class CoulombCounterError(ValueError):
    """安时积分输入非法。"""


@dataclass(frozen=True)
class SOCUpdate:
    """单步 SOC 更新结果。"""

    soc: float
    raw_soc: float
    delta_soc: float
    status: str


@dataclass
class CoulombCounter:
    """带限幅记录的单体安时积分器。"""

    capacity_ah: float
    soc: float
    charge_efficiency: float = 1.0
    discharge_efficiency: float = 1.0
    bound_events: list[dict[str, float | int | str]] = field(default_factory=list)
    step_count: int = 0

    def __post_init__(self) -> None:
        values = [self.capacity_ah, self.soc, self.charge_efficiency, self.discharge_efficiency]
        if not all(math.isfinite(float(value)) for value in values):
            raise CoulombCounterError("Non-finite parameter")
        if self.capacity_ah <= 0.0:
            raise CoulombCounterError("Invalid capacity")
        if not 0.0 <= self.soc <= 1.0:
            raise CoulombCounterError("Invalid initial SOC")
        if not 0.0 < self.charge_efficiency <= 1.0:
            raise CoulombCounterError("Invalid charge efficiency")
        if not 0.0 < self.discharge_efficiency <= 1.0:
            raise CoulombCounterError("Invalid discharge efficiency")

    @property
    def remaining_charge_ah(self) -> float:
        return float(self.soc * self.capacity_ah)

    @property
    def bound_count(self) -> int:
        return len(self.bound_events)

    def step(self, current_a: float, dt_s: float) -> SOCUpdate:
        """按零阶保持电流推进一个时间步。"""
        if not all(math.isfinite(float(value)) for value in (current_a, dt_s)):
            raise CoulombCounterError("Invalid sample")
        if dt_s <= 0.0:
            raise CoulombCounterError("Invalid time step")

        if current_a >= 0.0:
            effective_current = current_a / self.discharge_efficiency
        else:
            effective_current = current_a * self.charge_efficiency

        delta_soc = -effective_current * dt_s / (SECONDS_PER_HOUR * self.capacity_ah)
        raw_soc = self.soc + delta_soc
        limited_soc = min(max(raw_soc, 0.0), 1.0)
        status = "VALID" if 0.0 <= raw_soc <= 1.0 else "SOC_BOUND_REACHED"

        if status != "VALID":
            self.bound_events.append(
                {
                    "step": int(self.step_count),
                    "raw_soc": float(raw_soc),
                    "limited_soc": float(limited_soc),
                    "delta_soc": float(delta_soc),
                }
            )

        self.soc = limited_soc
        self.step_count += 1
        return SOCUpdate(soc=limited_soc, raw_soc=raw_soc, delta_soc=delta_soc, status=status)

    def reset(self, soc: float) -> None:
        """在明确参考状态处重新初始化（例如新实验会话开始）。"""
        if not math.isfinite(float(soc)) or not 0.0 <= float(soc) <= 1.0:
            raise CoulombCounterError("Invalid reset SOC")
        self.soc = float(soc)

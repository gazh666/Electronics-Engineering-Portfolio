"""容量更新与 SOC 自适应研究（Task 28）。

规则：

- 只有获得**新的有效完整容量实验**后，才允许更新后续会话使用的容量；
- 更新只能使用当前时刻已经完成的实验；
- 禁止用本循环最终测得的容量反向修正该循环开始时的在线 SOC 并称为实时
  自适应估计；
- 优先在已知参考状态或新实验会话开始时更新容量，运行中不得无依据突变 SOC。

``CapacityUpdater`` 通过会话边界（``begin_session``）强制这一时序约束。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class CapacityUpdateError(ValueError):
    """容量更新输入非法。"""


def update_capacity_estimate(
    previous_capacity_ah: float,
    measured_capacity_ah: float,
    smoothing_weight: float = 0.2,
) -> float:
    values = (previous_capacity_ah, measured_capacity_ah, smoothing_weight)
    if not all(math.isfinite(float(v)) for v in values):
        raise CapacityUpdateError("Invalid data")
    if min(float(previous_capacity_ah), float(measured_capacity_ah)) <= 0.0:
        raise CapacityUpdateError("Invalid capacity")
    if not 0.0 <= float(smoothing_weight) <= 1.0:
        raise CapacityUpdateError("Invalid weight")
    return float(previous_capacity_ah) + float(smoothing_weight) * (
        float(measured_capacity_ah) - float(previous_capacity_ah)
    )


@dataclass
class CapacityUpdater:
    """会话级容量更新器：只在会话开始时应用已完成实验的容量。"""

    active_capacity_ah: float
    smoothing_weight: float = 0.2
    pending_measurements_ah: list[float] = field(default_factory=list)
    history: list[dict[str, float | str]] = field(default_factory=list)
    session_index: int = 0

    def __post_init__(self) -> None:
        if float(self.active_capacity_ah) <= 0.0 or not math.isfinite(float(self.active_capacity_ah)):
            raise CapacityUpdateError("Invalid active capacity")
        if not 0.0 <= float(self.smoothing_weight) <= 1.0:
            raise CapacityUpdateError("Invalid smoothing weight")

    def record_completed_experiment(self, measured_capacity_ah: float) -> None:
        """记录一次已完成的完整容量实验（本会话内不立即生效）。"""
        if not math.isfinite(float(measured_capacity_ah)) or float(measured_capacity_ah) <= 0.0:
            raise CapacityUpdateError("Invalid measured capacity")
        self.pending_measurements_ah.append(float(measured_capacity_ah))

    def begin_session(self) -> float:
        """进入新实验会话：此刻才把已完成测量融合进活动容量。"""
        self.session_index += 1
        if self.pending_measurements_ah:
            previous = self.active_capacity_ah
            measured = float(self.pending_measurements_ah[-1])
            updated = update_capacity_estimate(previous, measured, self.smoothing_weight)
            self.history.append(
                {
                    "session_index": float(self.session_index),
                    "previous_capacity_ah": previous,
                    "measured_capacity_ah": measured,
                    "updated_capacity_ah": updated,
                    "note": "updated at session boundary",
                }
            )
            self.active_capacity_ah = updated
            self.pending_measurements_ah.clear()
        return float(self.active_capacity_ah)

    def undo_pending(self) -> None:
        """丢弃尚未生效的测量（例如实验被判无效）。"""
        self.pending_measurements_ah.clear()

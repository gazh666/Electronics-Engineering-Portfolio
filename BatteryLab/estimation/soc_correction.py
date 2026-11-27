"""安时积分 + 静置 OCV 校正（Task 11）。

公式：

``SOC_corrected = SOC_predicted + alpha × (SOC_ocv - SOC_predicted)``

``alpha`` 是校正权重，并额外限幅 ``|ΔSOC| ≤ maximum_correction``，防止一次
噪声很大的 OCV 读数把 SOC 拉飞。

为什么必须"调度"而不是每个采样点都乘同一 alpha：
若每来一个样本就乘 alpha，等效时间常数会随采样率变化（1 kHz 采样时收敛比
10 Hz 快 100 倍），物理上不可解释。因此用 ``SOCCorrectionScheduler`` 固定
每 ``correction_interval_s``（默认 60 s）才允许一次修正。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class CorrectionError(ValueError):
    """校正输入非法。"""


@dataclass(frozen=True)
class CorrectionResult:
    soc: float
    correction: float
    applied: bool
    reason: str


def correct_soc_from_ocv(
    predicted_soc: float,
    ocv_soc: float | None,
    eligible: bool,
    weight: float = 0.2,
    maximum_correction: float = 0.02,
) -> CorrectionResult:
    """按权重把 OCV 反演 SOC 融合进安时积分 SOC。"""
    if not math.isfinite(float(predicted_soc)):
        raise CorrectionError("Invalid predicted SOC")
    if not 0.0 <= float(predicted_soc) <= 1.0:
        raise CorrectionError("Invalid SOC range")
    if not math.isfinite(float(weight)) or not 0.0 <= float(weight) <= 1.0:
        raise CorrectionError("Invalid correction weight")
    if not math.isfinite(float(maximum_correction)) or float(maximum_correction) < 0.0:
        raise CorrectionError("Invalid correction limit")

    if not eligible or ocv_soc is None:
        return CorrectionResult(float(predicted_soc), 0.0, False, "CORRECTION_NOT_ELIGIBLE")

    if not math.isfinite(float(ocv_soc)) or not 0.0 <= float(ocv_soc) <= 1.0:
        return CorrectionResult(float(predicted_soc), 0.0, False, "INVALID_OCV_SOC")

    correction = float(weight) * (float(ocv_soc) - float(predicted_soc))
    correction = min(max(correction, -float(maximum_correction)), float(maximum_correction))
    corrected = min(max(float(predicted_soc) + correction, 0.0), 1.0)
    actual = corrected - float(predicted_soc)
    return CorrectionResult(corrected, actual, actual != 0.0, "VALID")


@dataclass
class SOCCorrectionScheduler:
    """固定时间间隔的校正调度器，附带完整事件记录。"""

    interval_s: float = 60.0
    weight: float = 0.2
    maximum_correction: float = 0.02
    last_correction_time_s: float | None = None
    correction_count: int = 0
    events: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.interval_s)) or float(self.interval_s) <= 0.0:
            raise CorrectionError("correction_interval_s 必须为正")
        if not 0.0 <= float(self.weight) <= 1.0:
            raise CorrectionError("correction weight 必须位于 [0,1]")
        if float(self.maximum_correction) < 0.0:
            raise CorrectionError("maximum_correction 不能为负")

    def reset(self) -> None:
        self.last_correction_time_s = None
        self.correction_count = 0
        self.events.clear()

    def due(self, time_s: float) -> bool:
        """距上次实际尝试校正是否已满一个间隔。"""
        if self.last_correction_time_s is None:
            return True
        return float(time_s) - self.last_correction_time_s >= float(self.interval_s)

    def apply(
        self,
        time_s: float,
        predicted_soc: float,
        ocv_soc: float | None,
        eligible: bool,
        *,
        rest_duration_s: float | None = None,
        voltage_slope_v_per_s: float | None = None,
    ) -> CorrectionResult | None:
        """若到调度点则执行一次校正并记录事件；否则返回 None。"""
        if not self.due(time_s):
            return None
        result = correct_soc_from_ocv(
            predicted_soc,
            ocv_soc,
            eligible,
            weight=self.weight,
            maximum_correction=self.maximum_correction,
        )
        self.last_correction_time_s = float(time_s)
        if result.applied:
            self.correction_count += 1
        self.events.append(
            {
                "time_s": float(time_s),
                "predicted_soc": float(predicted_soc),
                "ocv_soc": None if ocv_soc is None else float(ocv_soc),
                "correction": float(result.correction),
                "soc_after": float(result.soc),
                "applied": bool(result.applied),
                "reason": result.reason,
                "rest_duration_s": None if rest_duration_s is None else float(rest_duration_s),
                "voltage_slope_v_per_s": (
                    None if voltage_slope_v_per_s is None else float(voltage_slope_v_per_s)
                ),
            }
        )
        return result

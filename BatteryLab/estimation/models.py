"""第七阶段统一数据结构与采样序列质量检查。

时间轴约定：在区间 ``[t_k, t_k+1)`` 内使用 ``I_k`` 更新 SOC 与 RC 状态；
到达 ``t_k+1`` 后，才使用新时刻的测量电压计算电压残差。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np


class EstimationError(ValueError):
    """估计器输入或状态非法。"""


@dataclass(frozen=True)
class MeasurementSample:
    """单次测量快照。不可用测量必须显式置为 False，禁止静默填零。"""

    time_s: float
    current_a: float
    terminal_voltage_v: float
    temperature_c: float | None = None
    current_valid: bool = True
    voltage_valid: bool = True
    temperature_valid: bool = True

    def __post_init__(self) -> None:
        for value, name in (
            (self.time_s, "time_s"),
            (self.current_a, "current_a"),
            (self.terminal_voltage_v, "terminal_voltage_v"),
        ):
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise EstimationError(f"{name} 必须是有限数值")
        if self.temperature_c is not None and not math.isfinite(float(self.temperature_c)):
            raise EstimationError("temperature_c 必须是有限数值或 None")


@dataclass(frozen=True)
class SOCEstimate:
    """统一 SOC 估计输出。缺失值必须为 None，不能写成 0。"""

    time_s: float
    soc: float | None
    predicted_voltage_v: float | None
    voltage_residual_v: float | None
    correction_applied: bool
    method: str
    status: str


def samples_from_frame(frame: "Any") -> list[MeasurementSample]:
    """由 ``validation.dataset_split`` 的真实实验帧构造测量序列。

    只读取电流、端电压与温度，不读取 ``soc_reference``。
    """
    required = {"time_s", "current_a", "voltage_v"}
    missing = required.difference(frame.columns)
    if missing:
        raise EstimationError(f"实验帧缺少列: {sorted(missing)}")
    samples: list[MeasurementSample] = []
    temperature_present = "temperature_c" in frame.columns
    for row in frame.itertuples(index=False):
        temperature = float(row.temperature_c) if temperature_present and math.isfinite(float(row.temperature_c)) else None
        samples.append(
            MeasurementSample(
                time_s=float(row.time_s),
                current_a=float(row.current_a),
                terminal_voltage_v=float(row.voltage_v),
                temperature_c=temperature,
                temperature_valid=temperature is not None,
            )
        )
    return samples


def validate_sample_sequence(
    samples: Sequence[MeasurementSample],
    maximum_gap_s: float,
) -> dict[str, Any]:
    """检查时间戳严格递增与最大采样间隔，返回审计摘要。

    发现重复或倒退时间戳直接抛错；超过最大间隔只记录，交由回放器标记 DATA_GAP。
    """
    if len(samples) < 2:
        raise EstimationError("估计回放至少需要两个样本")
    if not math.isfinite(maximum_gap_s) or maximum_gap_s <= 0.0:
        raise EstimationError("最大采样间隔必须为正")
    times = np.asarray([sample.time_s for sample in samples], dtype=float)
    if not np.isfinite(times).all():
        raise EstimationError("时间轴包含非有限值")
    gaps = np.diff(times)
    if np.any(gaps <= 0.0):
        raise EstimationError("时间戳必须严格递增，禁止重复或倒退")
    gap_count = int(np.sum(gaps > maximum_gap_s))
    return {
        "sample_count": int(times.size),
        "duration_s": float(times[-1] - times[0]),
        "median_dt_s": float(np.median(gaps)),
        "maximum_dt_s": float(np.max(gaps)),
        "gap_count": gap_count,
        "maximum_gap_s": float(maximum_gap_s),
        "time_axis_status": "VALID" if gap_count == 0 else "CONTAINS_DATA_GAP",
    }


def mask_valid(values: Iterable[float | None]) -> np.ndarray:
    """把含 None 的估计序列转成布尔有效掩码。"""
    array = np.asarray([np.nan if value is None else float(value) for value in values], dtype=float)
    return np.isfinite(array)

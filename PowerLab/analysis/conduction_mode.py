"""CCM / DCM / 临界模式识别。

非同步 Buck 中，电感电流只能正向流动。实际 ngspice 波形由于开关关断电阻、
二极管漏电与数值误差，电流不会精确等于 0，因此不能只用 ``min == 0`` 判断 DCM。

本模块结合：
- 谷值 / 峰值电流；
- 绝对近零容差与相对峰值容差；
- 时间加权的近零持续时间占比；
- 明显反向电流异常。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

import numpy as np

from analysis.steady_state import slice_window
from circuits.validators import finite_number, nonnegative_number, positive_number

#: 默认绝对近零电流容差（A）。
DEFAULT_NEAR_ZERO_ABSOLUTE_A = 0.02

#: 默认相对峰值近零容差。
DEFAULT_NEAR_ZERO_RELATIVE = 0.02

#: 近零时间占比达到该值即判为 DCM。
DEFAULT_DCM_MINIMUM_RATIO = 0.02

#: 近零时间占比低于该值判为 CCM，其余为临界 / 不确定。
DEFAULT_BOUNDARY_RATIO = 0.005


class ConductionMode(str, Enum):
    """电感电流导通模式。"""

    CCM = "CCM"
    DCM = "DCM"
    BOUNDARY_OR_UNCERTAIN = "BOUNDARY_OR_UNCERTAIN"
    INVALID = "INVALID"
    NOT_SETTLED = "NOT_SETTLED"


@dataclass(frozen=True)
class ConductionModeResult:
    """导通模式识别结果与证据。"""

    mode: ConductionMode
    valley_current_a: float
    peak_current_a: float
    near_zero_threshold_a: float
    near_zero_time_ratio: float
    near_zero_duration_s: float
    cycles_analyzed: int
    reverse_current_anomaly: bool
    notes: str
    data_source: str = "spice_simulation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "valley_current_a": self.valley_current_a,
            "peak_current_a": self.peak_current_a,
            "near_zero_threshold_a": self.near_zero_threshold_a,
            "near_zero_time_ratio": self.near_zero_time_ratio,
            "near_zero_duration_s": self.near_zero_duration_s,
            "cycles_analyzed": self.cycles_analyzed,
            "reverse_current_anomaly": self.reverse_current_anomaly,
            "notes": self.notes,
            "data_source": self.data_source,
        }


def _validate(
    time_s: Any,
    inductor_current_a: Any,
) -> tuple[np.ndarray, np.ndarray]:
    time = np.asarray(time_s, dtype=float)
    current = np.asarray(inductor_current_a, dtype=float)
    if time.ndim != 1 or time.size < 2:
        raise ValueError("time_s must be a 1D array with at least two samples")
    if current.ndim != 1 or current.size != time.size:
        raise ValueError("inductor_current_a must have the same length as time_s")
    if not np.isfinite(time).all() or not np.isfinite(current).all():
        raise ValueError("time and current must be finite")
    if not np.all(np.diff(time) > 0):
        raise ValueError("time_s must be strictly increasing")
    return time, current


def time_fraction_below(
    time_s: Any,
    values: Any,
    threshold: float,
    *,
    start_s: float | None = None,
    end_s: float | None = None,
) -> tuple[float, float]:
    """时间加权低于 ``|threshold|`` 的占比与持续时间。

    使用梯形积分对 0/1 指示函数积分，避免按采样点数量统计导致偏差。
    """
    time, array = _validate(time_s, values)
    limit = nonnegative_number(threshold, "threshold")
    if start_s is not None or end_s is not None:
        if start_s is None or end_s is None:
            raise ValueError("start_s and end_s must be provided together")
        window_time, window_values = slice_window(time, array, start_s, end_s)
    else:
        window_time, window_values = time, array

    span = float(window_time[-1] - window_time[0])
    if span <= 0:
        raise ValueError("time span must be positive")
    indicator = (np.abs(window_values) <= limit).astype(float)
    if hasattr(np, "trapezoid"):
        duration = float(np.trapezoid(indicator, window_time))
    else:  # pragma: no cover - NumPy < 2
        duration = float(np.trapz(indicator, window_time))
    return duration / span, duration


def classify_conduction_mode(
    time_s: Any,
    inductor_current_a: Any,
    cycle_boundaries_s: Any,
    *,
    absolute_tolerance_a: float = DEFAULT_NEAR_ZERO_ABSOLUTE_A,
    relative_tolerance: float = DEFAULT_NEAR_ZERO_RELATIVE,
    dcm_minimum_near_zero_ratio: float = DEFAULT_DCM_MINIMUM_RATIO,
    boundary_ratio: float = DEFAULT_BOUNDARY_RATIO,
    reverse_relative_tolerance: float = 0.02,
) -> ConductionModeResult:
    """根据真实电感电流与完整周期边界识别导通模式。"""
    time, current = _validate(time_s, inductor_current_a)
    absolute = positive_number(absolute_tolerance_a, "absolute_tolerance_a")
    relative = nonnegative_number(relative_tolerance, "relative_tolerance")
    dcm_ratio = finite_number(dcm_minimum_near_zero_ratio, "dcm_minimum_near_zero_ratio")
    boundary = finite_number(boundary_ratio, "boundary_ratio")
    reverse_relative = nonnegative_number(reverse_relative_tolerance, "reverse_relative_tolerance")
    if not 0 <= boundary < dcm_ratio <= 1:
        raise ValueError("require 0 <= boundary_ratio < dcm_minimum_near_zero_ratio <= 1")

    boundaries = np.asarray(cycle_boundaries_s, dtype=float)
    if boundaries.ndim != 1 or boundaries.size < 2:
        return ConductionModeResult(
            mode=ConductionMode.INVALID,
            valley_current_a=float(current.min()),
            peak_current_a=float(current.max()),
            near_zero_threshold_a=absolute,
            near_zero_time_ratio=float("nan"),
            near_zero_duration_s=float("nan"),
            cycles_analyzed=0,
            reverse_current_anomaly=False,
            notes="no complete switching cycle available",
        )
    if not np.isfinite(boundaries).all() or not np.all(np.diff(boundaries) > 0):
        raise ValueError("cycle boundaries must be finite and strictly increasing")

    usable = boundaries[(boundaries >= time[0]) & (boundaries <= time[-1])]
    if usable.size < 2:
        return ConductionModeResult(
            mode=ConductionMode.INVALID,
            valley_current_a=float(current.min()),
            peak_current_a=float(current.max()),
            near_zero_threshold_a=absolute,
            near_zero_time_ratio=float("nan"),
            near_zero_duration_s=float("nan"),
            cycles_analyzed=0,
            reverse_current_anomaly=False,
            notes="cycle boundaries fall outside the recorded waveform",
        )

    _, window_current = slice_window(time, current, float(usable[0]), float(usable[-1]))
    peak = float(window_current.max())
    valley = float(window_current.min())
    scale = max(abs(peak), abs(valley), absolute)
    threshold = max(absolute, relative * scale)

    ratio, duration = time_fraction_below(
        time,
        current,
        threshold,
        start_s=float(usable[0]),
        end_s=float(usable[-1]),
    )

    reverse_limit = -max(3.0 * absolute, reverse_relative * scale)
    reverse_anomaly = bool(valley < reverse_limit)
    cycles = int(usable.size - 1)

    if reverse_anomaly:
        return ConductionModeResult(
            mode=ConductionMode.INVALID,
            valley_current_a=valley,
            peak_current_a=peak,
            near_zero_threshold_a=threshold,
            near_zero_time_ratio=ratio,
            near_zero_duration_s=duration,
            cycles_analyzed=cycles,
            reverse_current_anomaly=True,
            notes=(
                "inductor current goes clearly negative in an asynchronous buck; "
                "recorded as an anomaly instead of forcing a DCM label"
            ),
        )

    if ratio >= dcm_ratio:
        mode = ConductionMode.DCM
        note = "inductor current stays close to zero for a sustained part of the cycle"
    elif ratio <= boundary:
        mode = ConductionMode.CCM
        note = "inductor current remains above the near-zero band for the whole cycle"
    else:
        mode = ConductionMode.BOUNDARY_OR_UNCERTAIN
        note = "near-zero time ratio lies between the CCM and DCM thresholds"

    return ConductionModeResult(
        mode=mode,
        valley_current_a=valley,
        peak_current_a=peak,
        near_zero_threshold_a=threshold,
        near_zero_time_ratio=ratio,
        near_zero_duration_s=duration,
        cycles_analyzed=cycles,
        reverse_current_anomaly=False,
        notes=note,
    )


def theoretical_conduction_mode(
    boundary_current_a: float,
    average_output_current_a: float,
    *,
    relative_tolerance: float = 0.05,
) -> ConductionMode:
    """按理想临界电流给出理论工作模式（仅作对照）。"""
    boundary = positive_number(boundary_current_a, "boundary_current_a")
    average = nonnegative_number(average_output_current_a, "average_output_current_a")
    tolerance = finite_number(relative_tolerance, "relative_tolerance")
    if not 0 <= tolerance < 1:
        raise ValueError("relative_tolerance must be in [0, 1)")

    lower = boundary * (1.0 - tolerance)
    upper = boundary * (1.0 + tolerance)
    if average > upper:
        return ConductionMode.CCM
    if average < lower:
        return ConductionMode.DCM
    return ConductionMode.BOUNDARY_OR_UNCERTAIN


def mode_from_mapping(payload: Mapping[str, Any]) -> ConductionMode:
    """把 JSON 中的模式字符串还原为枚举（供验证模块使用）。"""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    value = payload.get("mode", payload.get("conduction_mode"))
    if isinstance(value, ConductionMode):
        return value
    if not isinstance(value, str):
        raise ValueError("payload does not contain a conduction mode string")
    try:
        return ConductionMode(value)
    except ValueError as exc:
        raise ValueError(f"unknown conduction mode: {value!r}") from exc

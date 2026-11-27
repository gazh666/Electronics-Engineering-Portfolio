"""PWM 调制器：载波、正弦载波占空比映射、真实波形脉冲分析。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from circuits.validators import finite_number, positive_number


def sine_carrier(time_s: float, frequency_hz: float) -> float:
    """0—1 正弦载波。"""
    t = finite_number(time_s, "time_s")
    fs = positive_number(frequency_hz, "frequency_hz")
    return 0.5 * (1.0 + math.sin(2.0 * math.pi * fs * t))


def sawtooth_carrier(time_s: float, frequency_hz: float) -> float:
    """0—1 锯齿载波（过零复位）。"""
    t = finite_number(time_s, "time_s")
    fs = positive_number(frequency_hz, "frequency_hz")
    phase = (t * fs) % 1.0
    return phase


def effective_duty_sine(threshold: float) -> float:
    """正弦载波比较器的平均占空比 D = 0.5 − asin(1 − 2d)/π。"""
    d = finite_number(threshold, "threshold")
    if not 0.0 <= d <= 1.0:
        raise ValueError("threshold must be within [0, 1]")
    return 0.5 - math.asin(1.0 - 2.0 * d) / math.pi


def threshold_from_effective_duty(duty: float) -> float:
    """正弦载波反解：由目标平均占空比得到比较阈值。"""
    value = finite_number(duty, "duty")
    if not 0.0 <= value <= 1.0:
        raise ValueError("duty must be within [0, 1]")
    return 0.5 * (1.0 - math.sin(math.pi * (0.5 - value)))


def sine_carrier_gain(threshold: float) -> float:
    """dD/dd = (2/π)/sqrt(1 − (1 − 2d)²)，在端点处退化。"""
    d = finite_number(threshold, "threshold")
    radicand = 1.0 - (1.0 - 2.0 * d) ** 2
    if radicand <= 1e-12:
        raise ValueError("carrier gain is singular at the rail; move threshold inward")
    return (2.0 / math.pi) / math.sqrt(radicand)


@dataclass(frozen=True)
class PWMPulseStatistics:
    """真实 PWM 波形的逐周期统计。"""

    cycles: int
    mean_duty: float
    minimum_duty: float
    maximum_duty: float
    multiple_pulse_cycles: int
    narrow_pulse_cycles: int
    missing_pulse_cycles: int
    maximum_pulses_per_cycle: int
    mean_frequency_hz: float
    valid: bool
    messages: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycles": self.cycles,
            "mean_duty": self.mean_duty,
            "minimum_duty": self.minimum_duty,
            "maximum_duty": self.maximum_duty,
            "multiple_pulse_cycles": self.multiple_pulse_cycles,
            "narrow_pulse_cycles": self.narrow_pulse_cycles,
            "missing_pulse_cycles": self.missing_pulse_cycles,
            "maximum_pulses_per_cycle": self.maximum_pulses_per_cycle,
            "mean_frequency_hz": self.mean_frequency_hz,
            "valid": self.valid,
            "messages": list(self.messages),
        }


def _crossings(time: np.ndarray, signal: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    shifted = signal - threshold
    previous = shifted[:-1]
    current = shifted[1:]
    rising = np.where((previous <= 0.0) & (current > 0.0))[0]
    falling = np.where((previous > 0.0) & (current <= 0.0))[0]

    def interpolate(indices: np.ndarray) -> np.ndarray:
        if indices.size == 0:
            return np.empty(0, dtype=float)
        y0 = shifted[indices]
        y1 = shifted[indices + 1]
        fraction = np.where(np.abs(y1 - y0) > 1e-15, -y0 / (y1 - y0), 0.0)
        return time[indices] + fraction * (time[indices + 1] - time[indices])

    return interpolate(rising), interpolate(falling)


def _on_intervals(
    rising: np.ndarray, falling: np.ndarray, end_time_s: float
) -> list[tuple[float, float]]:
    """把上升/下降沿配对成导通区间（允许首尾不完整）。"""
    starts: list[float] = list(rising)
    stops: list[float] = list(falling)
    if starts and (not stops or starts[0] > stops[0]):
        starts.insert(0, 0.0)
    while stops and len(stops) > len(starts):
        stops.pop(0)
    while len(starts) > len(stops):
        stops.append(end_time_s)
    return [
        (max(0.0, a), min(end_time_s, b))
        for a, b in zip(starts, stops)
        if b > a
    ]


def analyze_pwm_pulses(
    time_s: np.ndarray,
    pwm_signal: np.ndarray,
    period_s: float,
    *,
    threshold: float = 0.5,
    narrow_pulse_ratio: float = 0.01,
) -> tuple[pd.DataFrame, PWMPulseStatistics]:
    """按载波周期统计真实 PWM 波形。

    每个导通区间按中点归入所属周期（跨界脉冲只算一次），占空比仍按该周期
    内的重叠时间计算；``missing`` 只统计完全没有导通时间的周期。

    返回 ``(逐周期 DataFrame, 统计对象)``。逐周期列：
    ``index, start_s, end_s, pulses, on_time_s, duty, narrow_pulses``。
    """
    time = np.asarray(time_s, dtype=float)
    signal = np.asarray(pwm_signal, dtype=float)
    if time.shape != signal.shape or time.size < 3:
        raise ValueError("time and pwm_signal must be equally sized with >= 3 samples")
    period = positive_number(period_s, "period_s")
    level = finite_number(threshold, "threshold")
    if not 0.0 < level < 1.0:
        raise ValueError("threshold must be in (0, 1)")
    if np.any(np.diff(time) <= 0):
        raise ValueError("time must be strictly increasing")

    rising, falling = _crossings(time, signal, level)
    intervals = _on_intervals(rising, falling, float(time[-1]))

    cycle_index = np.floor(time / period).astype(int)
    first_cycle = int(cycle_index[0])
    last_cycle = int(cycle_index[-1])
    minimum_width = narrow_pulse_ratio * period

    rows: list[dict[str, float]] = []
    for index in range(first_cycle, last_cycle + 1):
        start = index * period
        end = start + period
        on_time = 0.0
        pulses = 0
        narrow = 0
        for a, b in intervals:
            # 一次导通的归属按区间中点判定：跨越周期边界的同一个脉冲只算一次，
            # 否则占空比大于 0.5 时每个周期都会被误判成“多次脉冲”。
            midpoint = 0.5 * (a + b)
            if start <= midpoint < end:
                width = b - a
                truncated = a <= time[0] or b >= time[-1]
                # 数据首尾被截断的极窄片段不是真实脉冲，不参与计数。
                if not (truncated and width < minimum_width):
                    pulses += 1
                    if width < minimum_width:
                        narrow += 1
            overlap = min(b, end) - max(a, start)
            if overlap > 0:
                on_time += overlap
        rows.append(
            {
                "index": index,
                "start_s": start,
                "end_s": end,
                "pulses": pulses,
                "on_time_s": on_time,
                "duty": on_time / period,
                "narrow_pulses": narrow,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("no complete carrier cycle was analysed")

    # 首末周期可能不完整，统计时剔除。
    complete = frame[(frame["start_s"] >= time[0]) & (frame["end_s"] <= time[-1])]
    used = complete if not complete.empty else frame
    duties = used["duty"].to_numpy(dtype=float)
    multiple = int((used["pulses"] > 1).sum())
    narrow_cycles = int((used["narrow_pulses"] > 0).sum())
    missing = int(((used["pulses"] == 0) & (used["on_time_s"] <= 1e-12)).sum())
    max_pulses = int(used["pulses"].max()) if len(used) else 0
    messages: list[str] = []
    if multiple:
        messages.append(f"{multiple} cycles contain multiple pulses")
    if narrow_cycles:
        messages.append(f"{narrow_cycles} cycles contain pulses narrower than 1% period")
    if missing:
        messages.append(f"{missing} cycles contain no pulse")
    if duties.size and (duties.min() < -1e-6 or duties.max() > 1.0 + 1e-6):
        messages.append("duty outside [0, 1]")
    valid = not messages

    mean_frequency = 0.0
    if used["pulses"].sum() > 0:
        span = float(used["end_s"].max() - used["start_s"].min())
        mean_frequency = float(used["pulses"].sum()) / span if span > 0 else 0.0

    stats = PWMPulseStatistics(
        cycles=int(len(used)),
        mean_duty=float(np.mean(duties)) if duties.size else float("nan"),
        minimum_duty=float(np.min(duties)) if duties.size else float("nan"),
        maximum_duty=float(np.max(duties)) if duties.size else float("nan"),
        multiple_pulse_cycles=multiple,
        narrow_pulse_cycles=narrow_cycles,
        missing_pulse_cycles=missing,
        maximum_pulses_per_cycle=max_pulses,
        mean_frequency_hz=mean_frequency,
        valid=valid,
        messages=tuple(messages),
    )
    return frame, stats


def measure_duty_windows(
    time_s: np.ndarray,
    pwm_signal: np.ndarray,
    window_s: float,
    *,
    threshold: float = 0.5,
) -> pd.DataFrame:
    """按固定窗口测量平均占空比，用于观察占空比饱和/变化。"""
    time = np.asarray(time_s, dtype=float)
    signal = np.asarray(pwm_signal, dtype=float)
    duration = positive_number(window_s, "window_s")
    level = finite_number(threshold, "threshold")
    high = signal > level
    index = np.floor((time - time[0]) / duration).astype(int)
    rows: list[dict[str, float]] = []
    for value in np.unique(index):
        mask = index == value
        segment_time = time[mask]
        if segment_time.size < 2:
            continue
        rows.append(
            {
                "start_s": float(segment_time[0]),
                "end_s": float(segment_time[-1]),
                "mean_duty": float(np.mean(high[mask])),
                "mean_signal": float(np.mean(signal[mask])),
            }
        )
    return pd.DataFrame(rows)

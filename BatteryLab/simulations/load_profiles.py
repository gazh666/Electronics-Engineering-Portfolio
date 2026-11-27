"""电流工况定义与时间轴生成（零阶保持 ZOH）。

约定：区间 ``[t_k, t_k+1)`` 使用 ``I_k``；t_k+1 处先更新连续状态，
再按新电流计算端电压，因此端电压允许因 R0 产生瞬时跳变。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd


class ProfileError(ValueError):
    """电流工况非法。"""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ProfileError(f"{name} 不允许使用布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ProfileError(f"{name} 必须是数值") from exc
    if not math.isfinite(number):
        raise ProfileError(f"{name} 必须是有限数值")
    return number


@dataclass(frozen=True)
class CurrentSegment:
    duration_s: float
    current_a: float
    label: str = ""

    def __post_init__(self) -> None:
        duration = _finite(self.duration_s, "段时长")
        current = _finite(self.current_a, "段电流")
        if duration <= 0.0:
            raise ProfileError("段时长必须为正数")
        object.__setattr__(self, "duration_s", duration)
        object.__setattr__(self, "current_a", current)


@dataclass
class LoadProfile:
    """分段恒流工况。"""

    name: str
    segments: tuple[CurrentSegment, ...]
    description: str = ""
    data_source: str = "custom_ecm_simulation"

    def __post_init__(self) -> None:
        if not self.segments:
            raise ProfileError("工况至少需要一个电流段")

    @property
    def duration_s(self) -> float:
        return float(sum(segment.duration_s for segment in self.segments))

    @property
    def boundaries_s(self) -> tuple[float, ...]:
        times = [0.0]
        for segment in self.segments:
            times.append(times[-1] + segment.duration_s)
        return tuple(times)

    def events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for index in range(1, len(self.segments)):
            before = self.segments[index - 1].current_a
            after = self.segments[index].current_a
            if abs(after - before) > 1e-12:
                events.append(
                    {
                        "event_type": "current_step",
                        "time_s": self.boundaries_s[index],
                        "current_before_a": before,
                        "current_after_a": after,
                        "label_before": self.segments[index - 1].label,
                        "label_after": self.segments[index].label,
                    }
                )
        return events

    def current_at(self, time_s: float) -> float:
        target = float(time_s)
        if target < 0.0 or target > self.duration_s + 1e-9:
            raise ProfileError("查询时刻超出工况范围")
        elapsed = 0.0
        for segment in self.segments:
            elapsed += segment.duration_s
            if target < elapsed - 1e-12:
                return segment.current_a
        return self.segments[-1].current_a

    def label_at(self, time_s: float) -> str:
        target = float(time_s)
        elapsed = 0.0
        for segment in self.segments:
            elapsed += segment.duration_s
            if target < elapsed - 1e-12:
                return segment.label
        return self.segments[-1].label

    def sample(self, output_step_s: float) -> tuple[np.ndarray, np.ndarray]:
        """生成包含所有电流阶跃边界的输出时间轴与 ZOH 电流。"""
        step = _finite(output_step_s, "输出时间间隔")
        if step <= 0.0:
            raise ProfileError("输出时间间隔必须为正数")
        duration = self.duration_s
        count = int(math.floor(duration / step + 1e-9))
        base = np.round(np.arange(count + 1, dtype=float) * step, 9)
        candidates = list(base) + list(self.boundaries_s)
        candidates = [value for value in candidates if value <= duration + 1e-9]
        times = _unique_increasing(candidates)
        currents = np.array([self.current_at(value) for value in times], dtype=float)
        return times, currents

    def metadata(self) -> dict[str, Any]:
        return {
            "profile_name": self.name,
            "description": self.description,
            "duration_s": self.duration_s,
            "data_source": self.data_source,
            "segments": [
                {"duration_s": segment.duration_s, "current_a": segment.current_a, "label": segment.label}
                for segment in self.segments
            ],
            "events": self.events(),
        }


def _unique_increasing(values: Sequence[float]) -> np.ndarray:
    ordered = sorted(float(value) for value in values)
    result: list[float] = []
    for value in ordered:
        if not result or value - result[-1] > 1e-9:
            result.append(value)
    return np.asarray(result, dtype=float)


def constant_current_profile(current_a: float, duration_s: float, *, name: str | None = None) -> LoadProfile:
    label = "discharge" if current_a > 0 else ("charge" if current_a < 0 else "rest")
    return LoadProfile(
        name=name or f"constant_{label}",
        segments=(CurrentSegment(duration_s, current_a, label),),
        description=f"{current_a:g} A 恒流 {duration_s:g} s",
    )


def rest_profile(duration_s: float, *, name: str = "rest") -> LoadProfile:
    return LoadProfile(name=name, segments=(CurrentSegment(duration_s, 0.0, "rest"),), description=f"静置 {duration_s:g} s")


def single_pulse_profile(
    *,
    rest_before_s: float = 10.0,
    pulse_current_a: float = 2.0,
    pulse_duration_s: float = 60.0,
    rest_after_s: float = 120.0,
    name: str = "single_pulse",
) -> LoadProfile:
    return LoadProfile(
        name=name,
        segments=(
            CurrentSegment(rest_before_s, 0.0, "rest_initial"),
            CurrentSegment(
                pulse_duration_s, pulse_current_a, "discharge_pulse" if pulse_current_a > 0 else "charge_pulse"
            ),
            CurrentSegment(rest_after_s, 0.0, "rest_recovery"),
        ),
        description=f"{pulse_current_a:g} A 脉冲 {pulse_duration_s:g} s",
    )


def multi_pulse_profile(
    *,
    rest_before_s: float = 10.0,
    pulse_current_a: float = 2.0,
    pulse_duration_s: float = 30.0,
    rest_between_s: float = 30.0,
    pulse_count: int = 3,
    rest_after_s: float = 60.0,
    name: str = "multi_pulse",
) -> LoadProfile:
    if pulse_count < 1:
        raise ProfileError("脉冲次数必须至少为 1")
    segments = [CurrentSegment(rest_before_s, 0.0, "rest_initial")]
    for index in range(pulse_count):
        segments.append(CurrentSegment(pulse_duration_s, pulse_current_a, f"pulse_{index + 1}"))
        segments.append(CurrentSegment(rest_between_s, 0.0, f"rest_{index + 1}"))
    segments.append(CurrentSegment(rest_after_s, 0.0, "rest_recovery"))
    return LoadProfile(name=name, segments=tuple(segments), description=f"{pulse_count} 次脉冲")


def piecewise_profile(
    segments: Sequence[tuple[float, float] | CurrentSegment | dict[str, Any]],
    *,
    name: str = "piecewise",
    description: str = "",
    data_source: str = "custom_ecm_simulation",
) -> LoadProfile:
    """由 (时长, 电流) 元组、CurrentSegment 或字典构造分段工况。"""
    built: list[CurrentSegment] = []
    for index, item in enumerate(segments):
        if isinstance(item, CurrentSegment):
            built.append(item)
        elif isinstance(item, dict):
            built.append(
                CurrentSegment(
                    item["duration_s"],
                    item["current_a"],
                    str(item.get("label", f"segment_{index + 1}")),
                )
            )
        else:
            duration, current = item
            label = "discharge" if current > 0 else ("charge" if current < 0 else "rest")
            built.append(CurrentSegment(duration, current, f"{label}_{index + 1}"))
    return LoadProfile(
        name=name,
        segments=tuple(built),
        description=description,
        data_source=data_source,
    )


@dataclass
class ArrayProfile:
    """基于真实实验数组的电流工况（CALCE 重放）。

    原始采样时刻保留；若需要统一网格，可调用 ``sample`` 进行 ZOH 重采样。
    """

    name: str
    time_s: np.ndarray
    current_a: np.ndarray
    description: str = ""
    data_source: str = "public_experimental_data"
    sampling_assumption: str = "zero_order_hold_replay"
    notes: list[str] | None = None

    def __post_init__(self) -> None:
        time_array = np.asarray(self.time_s, dtype=float)
        current_array = np.asarray(self.current_a, dtype=float)
        if time_array.ndim != 1 or current_array.ndim != 1:
            raise ProfileError("时间与电流必须是一维数组")
        if time_array.size != current_array.size or time_array.size < 2:
            raise ProfileError("时间与电流长度必须一致且至少两个点")
        if not np.isfinite(time_array).all() or not np.isfinite(current_array).all():
            raise ProfileError("时间与电流必须为有限数值")
        if not np.all(np.diff(time_array) > 0.0):
            raise ProfileError("实验时间必须严格递增")
        self.time_s = time_array
        self.current_a = current_array
        self.notes = list(self.notes or [])

    @property
    def duration_s(self) -> float:
        return float(self.time_s[-1] - self.time_s[0])

    def events(self, threshold_a: float = 1e-9) -> list[dict[str, Any]]:
        events = []
        for index in range(1, self.current_a.size):
            delta = float(self.current_a[index] - self.current_a[index - 1])
            if abs(delta) > threshold_a:
                events.append(
                    {
                        "event_type": "current_change",
                        "time_s": float(self.time_s[index]),
                        "current_before_a": float(self.current_a[index - 1]),
                        "current_after_a": float(self.current_a[index]),
                        "delta_current_a": delta,
                    }
                )
        return events

    def sample(self, output_step_s: float, *, start_from_zero: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """按统一时间步长对实验电流做 ZOH 重采样（不外推）。"""
        step = _finite(output_step_s, "输出时间间隔")
        if step <= 0.0:
            raise ProfileError("输出时间间隔必须为正")
        duration = self.duration_s
        count = int(math.floor(duration / step + 1e-9))
        relative = np.round(np.arange(count + 1, dtype=float) * step, 9)
        absolute = relative + (self.time_s[0] if not start_from_zero else 0.0)
        absolute = np.minimum(absolute, self.time_s[-1])
        current = np.interp(absolute, self.time_s, self.current_a, left=self.current_a[0], right=self.current_a[-1])
        return absolute, current

    def metadata(self) -> dict[str, Any]:
        return {
            "profile_name": self.name,
            "description": self.description,
            "data_source": self.data_source,
            "sampling_assumption": self.sampling_assumption,
            "points": int(self.time_s.size),
            "time_start_s": float(self.time_s[0]),
            "time_end_s": float(self.time_s[-1]),
            "current_min_a": float(self.current_a.min()),
            "current_max_a": float(self.current_a.max()),
            "notes": self.notes,
        }


def profile_from_arrays(
    time_s: Sequence[float],
    current_a: Sequence[float],
    *,
    name: str,
    description: str = "",
    max_gap_s: float | None = None,
    max_points: int | None = None,
    data_source: str = "public_experimental_data",
) -> ArrayProfile:
    """从真实实验数组构造重放工况。

    - 重复时间戳保留首个样本。
    - ``max_gap_s`` 指定时，在首个超过该间隔的位置截断，避免跨越不连续实验段。
    - ``max_points`` 指定时按等步长抽取，抽取比例写入 notes，不改变原始数据文件。
    """
    time_array = np.asarray(time_s, dtype=float)
    current_array = np.asarray(current_a, dtype=float)
    if time_array.size != current_array.size:
        raise ProfileError("时间与电流长度不一致")
    notes: list[str] = []
    keep = [0]
    for index in range(1, time_array.size):
        if time_array[index] <= time_array[keep[-1]] + 1e-12:
            continue
        keep.append(index)
    if len(keep) != time_array.size:
        notes.append(f"去除重复时间戳 {time_array.size - len(keep)} 点")
    time_array = time_array[keep]
    current_array = current_array[keep]

    if max_gap_s is not None and max_gap_s > 0:
        gaps = np.diff(time_array)
        exceed = np.where(gaps > float(max_gap_s))[0]
        if exceed.size:
            cut = int(exceed[0]) + 1
            notes.append(
                f"在 t={time_array[cut]:.3f}s 处检测到 {gaps[exceed[0]]:.3f}s 数据间隔，截断为连续片段"
            )
            time_array = time_array[:cut]
            current_array = current_array[:cut]

    if max_points is not None and max_points > 0 and time_array.size > int(max_points):
        stride = int(math.ceil(time_array.size / float(max_points)))
        index = list(range(0, time_array.size, stride))
        if index[-1] != time_array.size - 1:
            index.append(time_array.size - 1)
        notes.append(f"等步长抽取 stride={stride}，仅用于教学重放，原始文件未修改")
        time_array = time_array[index]
        current_array = current_array[index]

    return ArrayProfile(
        name=name,
        time_s=time_array,
        current_a=current_array,
        description=description,
        data_source=data_source,
        notes=notes,
    )


def profile_from_frame(
    frame: pd.DataFrame,
    *,
    name: str,
    time_column: str = "time_s",
    current_column: str = "current_a",
    max_gap_s: float | None = None,
    max_points: int | None = None,
) -> ArrayProfile:
    if time_column not in frame.columns or current_column not in frame.columns:
        raise ProfileError("数据表缺少时间或电流列")
    return profile_from_arrays(
        frame[time_column].to_numpy(dtype=float),
        frame[current_column].to_numpy(dtype=float),
        name=name,
        description="公开实验电流重放（符号已统一为放电为正）",
        max_gap_s=max_gap_s,
        max_points=max_points,
    )

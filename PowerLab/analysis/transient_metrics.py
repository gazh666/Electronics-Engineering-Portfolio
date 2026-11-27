"""第七阶段瞬态指标：事件前后均值、跌落/过冲、恢复时间、IAE/ISE。

数据来源可以是真实 SPICE 波形，也可以是平均模型波形；调用方必须通过
``data_source`` 明确标注，本模块不会把平均模型当成开关波形。

恢复时间定义
------------
- ``strict``：在相邻扰动事件之间，先用开关周期均值压缩波形，再寻找第一个
  连续保持 ``hold_time_s``（至少 ``hold_cycles`` 个周期）都落在容差带内的时刻。
- ``loose``：直接在原始采样点上寻找同样的保持窗口，通常更早，但对纹波敏感。

两种结果都保存。找不到时返回 ``NOT_RECOVERED`` 与 ``NaN``，不用 0 或末尾时间代替。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from circuits.validators import finite_number, positive_number


@dataclass(frozen=True)
class DisturbanceEvent:
    """一次负载或输入扰动事件。"""

    event_id: str
    event_type: str
    start_time_s: float
    end_time_s: float
    initial_value: float
    final_value: float
    unit: str = "A"

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ValueError("event_type must be a non-empty string")
        start = finite_number(self.start_time_s, "event.start_time_s")
        end = finite_number(self.end_time_s, "event.end_time_s")
        if start < 0:
            raise ValueError("event.start_time_s must be nonnegative")
        if end < start:
            raise ValueError("event.end_time_s must not precede start_time_s")

    @property
    def step_size(self) -> float:
        return self.final_value - self.initial_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "initial_value": self.initial_value,
            "final_value": self.final_value,
            "step_size": self.step_size,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class RecoveryResult:
    status: str
    recovery_time_s: float
    mode: str
    hold_time_s: float
    tolerance_v: float
    checked_from_s: float
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "recovery_time_s": self.recovery_time_s
            if math.isfinite(self.recovery_time_s)
            else None,
            "mode": self.mode,
            "hold_time_s": self.hold_time_s,
            "tolerance_v": self.tolerance_v,
            "checked_from_s": self.checked_from_s,
            "notes": list(self.notes),
        }


def _validate_series(time_s: Iterable[float], values: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
    time = np.asarray(list(time_s), dtype=float)
    data = np.asarray(list(values), dtype=float)
    if time.size != data.size:
        raise ValueError("time and values must have equal length")
    if time.size < 3:
        raise ValueError("at least three samples are required")
    if not np.all(np.isfinite(time)):
        raise ValueError("time contains non-finite values")
    if np.any(np.diff(time) <= 0):
        raise ValueError("time must be strictly increasing")
    return time, data


def cycle_mean_waveform(
    time_s: Iterable[float],
    values: Iterable[float],
    period_s: float,
    *,
    start_s: float | None = None,
    stop_s: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """按开关周期分箱求均值，返回 ``(周期中心时间, 周期均值)``。"""
    period = positive_number(period_s, "period_s")
    time, data = _validate_series(time_s, values)
    mask = np.isfinite(data)
    if start_s is not None:
        mask &= time >= start_s
    if stop_s is not None:
        mask &= time <= stop_s
    if not np.any(mask):
        return np.empty(0), np.empty(0)
    bins = np.floor((time[mask] - time[mask][0]) / period).astype(int)
    frame = pd.DataFrame({"bin": bins, "time": time[mask], "value": data[mask]})
    grouped = frame.groupby("bin", sort=True)
    centers = grouped["time"].mean().to_numpy()
    means = grouped["value"].mean().to_numpy()
    return centers, means


def _hold_window(
    time: np.ndarray,
    values: np.ndarray,
    *,
    target: float,
    tolerance: float,
    hold_time: float,
    start_index: int,
    end_time: float,
) -> tuple[int, tuple[str, ...]]:
    notes: list[str] = []
    index = start_index
    while index < time.size:
        if abs(values[index] - target) > tolerance:
            index += 1
            continue
        deadline = time[index] + hold_time
        if deadline > end_time + 1e-15:
            notes.append("insufficient remaining time for the full hold window")
            return -1, tuple(notes)
        window = (time >= time[index]) & (time <= deadline)
        if np.all(np.abs(values[window] - target) <= tolerance):
            return index, tuple(notes)
        # 跳过当前不满足保持窗口的样本，避免 O(n^2) 大范围重复扫描。
        bad = np.where(np.abs(values[window] - target) > tolerance)[0]
        if bad.size == 0:
            return index, tuple(notes)
        index += int(bad[-1]) + 1
        if index >= time.size:
            break
    notes.append("no interval satisfied the hold requirement")
    return -1, tuple(notes)


def find_recovery_time(
    time_s: Iterable[float],
    voltage_v: Iterable[float],
    *,
    event_end_s: float,
    target_v: float,
    tolerance_v: float,
    period_s: float,
    hold_cycles: int = 20,
    next_event_s: float | None = None,
    mode: str = "strict",
) -> RecoveryResult:
    """寻找恢复时间；``mode`` 为 ``strict``（周期均值）或 ``loose``（原始包络）。"""
    if mode not in ("strict", "loose"):
        raise ValueError("mode must be 'strict' or 'loose'")
    tolerance = positive_number(tolerance_v, "tolerance_v")
    target = finite_number(target_v, "target_v")
    period = positive_number(period_s, "period_s")
    if not isinstance(hold_cycles, int) or hold_cycles < 1:
        raise ValueError("hold_cycles must be a positive integer")
    time, data = _validate_series(time_s, voltage_v)
    end_time = float(time[-1]) if next_event_s is None else min(float(next_event_s), float(time[-1]))
    start = float(event_end_s)
    if start >= end_time:
        return RecoveryResult(
            status="INSUFFICIENT_DATA",
            recovery_time_s=math.nan,
            mode=mode,
            hold_time_s=hold_cycles * period,
            tolerance_v=tolerance,
            checked_from_s=start,
            notes=("no post-event data",),
        )
    hold_time = hold_cycles * period
    if mode == "strict":
        centers, means = cycle_mean_waveform(time, data, period, start_s=start, stop_s=end_time)
        if centers.size < 2:
            return RecoveryResult(
                status="INSUFFICIENT_DATA",
                recovery_time_s=math.nan,
                mode=mode,
                hold_time_s=hold_time,
                tolerance_v=tolerance,
                checked_from_s=start,
                notes=("fewer than two complete cycles after the event",),
            )
        index, notes = _hold_window(
            centers, means, target=target, tolerance=tolerance,
            hold_time=hold_time, start_index=0, end_time=end_time,
        )
        if index < 0:
            return RecoveryResult(
                status="NOT_RECOVERED", recovery_time_s=math.nan, mode=mode,
                hold_time_s=hold_time, tolerance_v=tolerance,
                checked_from_s=start, notes=notes,
            )
        return RecoveryResult(
            status="OK", recovery_time_s=float(centers[index]), mode=mode,
            hold_time_s=hold_time, tolerance_v=tolerance,
            checked_from_s=start, notes=notes,
        )

    mask = (time >= start) & (time <= end_time)
    subset_time = time[mask]
    subset_values = data[mask]
    if subset_time.size < 3:
        return RecoveryResult(
            status="INSUFFICIENT_DATA", recovery_time_s=math.nan, mode=mode,
            hold_time_s=hold_time, tolerance_v=tolerance,
            checked_from_s=start, notes=("too few raw samples after the event",),
        )
    index, notes = _hold_window(
        subset_time, subset_values, target=target, tolerance=tolerance,
        hold_time=hold_time, start_index=0, end_time=end_time,
    )
    if index < 0:
        return RecoveryResult(
            status="NOT_RECOVERED", recovery_time_s=math.nan, mode=mode,
            hold_time_s=hold_time, tolerance_v=tolerance,
            checked_from_s=start, notes=notes,
        )
    return RecoveryResult(
        status="OK", recovery_time_s=float(subset_time[index]), mode=mode,
        hold_time_s=hold_time, tolerance_v=tolerance,
        checked_from_s=start, notes=notes,
    )


def _mean_over(
    time: np.ndarray, values: np.ndarray, start: float, stop: float
) -> float:
    mask = (time >= start) & (time <= stop) & np.isfinite(values)
    if not np.any(mask):
        return math.nan
    return float(np.mean(values[mask]))


def analyze_event(
    time_s: Iterable[float],
    voltage_v: Iterable[float],
    event: DisturbanceEvent,
    *,
    target_v: float,
    tolerance_v: float,
    period_s: float,
    hold_cycles: int = 20,
    pre_window_s: float = 1e-3,
    next_event_s: float | None = None,
    data_source: str = "spice_simulation",
) -> dict[str, Any]:
    """计算单个扰动事件的完整指标；不足数据时明确返回状态。"""
    time, data = _validate_series(time_s, voltage_v)
    period = positive_number(period_s, "period_s")
    target = finite_number(target_v, "target_v")
    tolerance = positive_number(tolerance_v, "tolerance_v")
    pre_start = max(0.0, event.start_time_s - pre_window_s)
    pre_mask = (time >= pre_start) & (time < event.start_time_s) & np.isfinite(data)
    pre_mean = float(np.mean(data[pre_mask])) if np.any(pre_mask) else math.nan
    post_end = float(time[-1]) if next_event_s is None else min(float(next_event_s), float(time[-1]))
    post_start = event.end_time_s
    post_mask = (time >= post_start) & (time <= post_end) & np.isfinite(data)
    result: dict[str, Any] = {
        "event": event.to_dict(),
        "data_source": data_source,
        "target_v": target,
        "tolerance_v": tolerance,
        "period_s": period,
        "pre_window_s": pre_window_s,
        "post_window_s": post_end - post_start,
        "pre_event_mean_v": pre_mean,
        "post_event_mean_v": math.nan,
        "post_event_min_v": math.nan,
        "post_event_max_v": math.nan,
        "post_event_peak_time_s": math.nan,
        "droop_v": math.nan,
        "overshoot_v": math.nan,
        "maximum_absolute_deviation_v": math.nan,
        "maximum_relative_deviation_percent": math.nan,
        "final_mean_v": math.nan,
        "steady_state_error_v": math.nan,
        "iae_vs": math.nan,
        "ise_v2s": math.nan,
        "recovery_strict": None,
        "recovery_loose": None,
        "status": "NOT_RESOLVED",
        "notes": [],
    }
    if not np.any(post_mask) or post_start >= post_end:
        result["status"] = "INSUFFICIENT_DATA"
        result["notes"].append("no samples inside the post-event window")
        return result

    post_time = time[post_mask]
    post_values = data[post_mask]
    maximum = float(np.max(post_values))
    minimum = float(np.min(post_values))
    if not math.isfinite(pre_mean):
        result["status"] = "INSUFFICIENT_DATA"
        result["notes"].append("no samples inside the pre-event window")
        result["pre_event_mean_v"] = math.nan
        reference = target
    else:
        reference = pre_mean
    peak_index = int(np.argmax(np.abs(post_values - reference)))
    result.update(
        {
            "post_event_mean_v": float(np.mean(post_values)),
            "post_event_min_v": minimum,
            "post_event_max_v": maximum,
            "post_event_peak_time_s": float(post_time[peak_index]),
            "droop_v": max(0.0, reference - minimum),
            "overshoot_v": max(0.0, maximum - reference),
            "maximum_absolute_deviation_v": float(abs(post_values[peak_index] - reference)),
            "maximum_relative_deviation_percent": (
                100.0 * float(abs(post_values[peak_index] - reference)) / abs(reference)
                if reference != 0
                else math.nan
            ),
            "iae_vs": float(np.trapz(np.abs(post_values - target), post_time)),
            "ise_v2s": float(np.trapz((post_values - target) ** 2, post_time)),
        }
    )
    tail_start = max(post_start, post_end - max(10.0 * period, 0.2 * (post_end - post_start)))
    final_mean = _mean_over(time, data, tail_start, post_end)
    result["final_mean_v"] = final_mean
    result["steady_state_error_v"] = (
        final_mean - target if math.isfinite(final_mean) else math.nan
    )

    strict = find_recovery_time(
        time, data, event_end_s=post_start, target_v=target, tolerance_v=tolerance,
        period_s=period, hold_cycles=hold_cycles, next_event_s=next_event_s, mode="strict",
    )
    loose = find_recovery_time(
        time, data, event_end_s=post_start, target_v=target, tolerance_v=tolerance,
        period_s=period, hold_cycles=hold_cycles, next_event_s=next_event_s, mode="loose",
    )
    result["recovery_strict"] = strict.to_dict()
    result["recovery_loose"] = loose.to_dict()
    result["status"] = "OK"
    if strict.status == "NOT_RECOVERED":
        result["notes"].append("strict cycle-mean recovery not reached before the simulation end")
    if loose.status == "NOT_RECOVERED":
        result["notes"].append("raw-envelope recovery not reached before the simulation end")
    return result


def analyze_events(
    time_s: Iterable[float],
    voltage_v: Iterable[float],
    events: Iterable[DisturbanceEvent],
    *,
    target_v: float,
    tolerance_v: float,
    period_s: float,
    hold_cycles: int = 20,
    pre_window_s: float = 1e-3,
    data_source: str = "spice_simulation",
) -> list[dict[str, Any]]:
    """按时间顺序分析多个事件，自动截断到下一个事件起点。"""
    ordered = sorted(events, key=lambda item: item.start_time_s)
    results: list[dict[str, Any]] = []
    for index, event in enumerate(ordered):
        next_start = ordered[index + 1].start_time_s if index + 1 < len(ordered) else None
        results.append(
            analyze_event(
                time_s, voltage_v, event, target_v=target_v, tolerance_v=tolerance_v,
                period_s=period_s, hold_cycles=hold_cycles, pre_window_s=pre_window_s,
                next_event_s=next_start, data_source=data_source,
            )
        )
    return results


def summarize_event_metrics(metrics: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """把事件指标压成便于 CSV 导出的表。"""
    rows: list[dict[str, Any]] = []
    for item in metrics:
        event = item.get("event", {})
        strict = item.get("recovery_strict") or {}
        loose = item.get("recovery_loose") or {}
        rows.append(
            {
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "start_time_s": event.get("start_time_s"),
                "pre_event_mean_v": item.get("pre_event_mean_v"),
                "post_event_min_v": item.get("post_event_min_v"),
                "post_event_max_v": item.get("post_event_max_v"),
                "droop_v": item.get("droop_v"),
                "overshoot_v": item.get("overshoot_v"),
                "maximum_absolute_deviation_v": item.get("maximum_absolute_deviation_v"),
                "maximum_relative_deviation_percent": item.get("maximum_relative_deviation_percent"),
                "final_mean_v": item.get("final_mean_v"),
                "steady_state_error_v": item.get("steady_state_error_v"),
                "iae_vs": item.get("iae_vs"),
                "ise_v2s": item.get("ise_v2s"),
                "recovery_strict_s": strict.get("recovery_time_s"),
                "recovery_strict_status": strict.get("status"),
                "recovery_loose_s": loose.get("recovery_time_s"),
                "recovery_loose_status": loose.get("status"),
                "status": item.get("status"),
                "data_source": item.get("data_source"),
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "DisturbanceEvent",
    "RecoveryResult",
    "analyze_event",
    "analyze_events",
    "cycle_mean_waveform",
    "find_recovery_time",
    "summarize_event_metrics",
]

"""开关边沿、延迟与开关能量分析。

所有时间点由真实波形线性插值得到；不做多项式拟合、不做平滑后取交点。

若边沿内的原始采样点不足 ``minimum_edge_samples``，结果标记 ``NOT_RESOLVED``，
而不是给出一个看似精确的假值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .time_domain import validate_time_series


@dataclass(frozen=True)
class EdgeTiming:
    """单次（或多次平均后的）边沿时间。"""

    name: str
    status: str
    start_time_s: float | None
    end_time_s: float | None
    duration_s: float | None
    sample_count: int
    max_gap_s: float | None
    note: str = ""
    data_source: str = "spice_derived"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "duration_s": self.duration_s,
            "sample_count": self.sample_count,
            "max_gap_s": self.max_gap_s,
            "note": self.note,
            "data_source": self.data_source,
        }


@dataclass(frozen=True)
class SwitchingAnalysis:
    vds_low_v: float
    vds_high_v: float
    low_threshold_v: float
    high_threshold_v: float
    turn_on: EdgeTiming
    turn_off: EdgeTiming
    turn_on_delay_s: float | None
    turn_off_delay_s: float | None
    edge_count: int
    cycle_energy_j: float | None
    turn_on_energy_j: float | None
    turn_off_energy_j: float | None
    switching_power_w: float | None
    data_source: str = "spice_derived"

    def to_dict(self) -> dict[str, Any]:
        return {
            "vds_low_v": self.vds_low_v,
            "vds_high_v": self.vds_high_v,
            "low_threshold_v": self.low_threshold_v,
            "high_threshold_v": self.high_threshold_v,
            "turn_on": self.turn_on.to_dict(),
            "turn_off": self.turn_off.to_dict(),
            "turn_on_delay_s": self.turn_on_delay_s,
            "turn_off_delay_s": self.turn_off_delay_s,
            "edge_count": self.edge_count,
            "cycle_energy_j": self.cycle_energy_j,
            "turn_on_energy_j": self.turn_on_energy_j,
            "turn_off_energy_j": self.turn_off_energy_j,
            "switching_power_w": self.switching_power_w,
            "method": "linear_interpolation_of_raw_vds_samples",
            "data_source": self.data_source,
        }


def interpolate_crossing(
    time_s: Any,
    values: Any,
    threshold: float,
    *,
    rising: bool,
    start_time_s: float | None = None,
    end_time_s: float | None = None,
) -> float | None:
    """查找首次越过 ``threshold`` 的时刻，返回线性插值时间。"""
    time, array = validate_time_series(time_s, values)
    level = float(threshold)
    start = float(time[0]) if start_time_s is None else float(start_time_s)
    end = float(time[-1]) if end_time_s is None else float(end_time_s)
    for index in range(1, time.size):
        left_t, right_t = float(time[index - 1]), float(time[index])
        if right_t < start or left_t > end:
            continue
        left_v, right_v = float(array[index - 1]), float(array[index])
        crossed = (left_v < level <= right_v) if rising else (left_v > level >= right_v)
        if not crossed or right_v == left_v:
            continue
        fraction = (level - left_v) / (right_v - left_v)
        crossing = left_t + fraction * (right_t - left_t)
        if start <= crossing <= end:
            return float(crossing)
    return None


def _transition_intervals(
    time: np.ndarray,
    values: np.ndarray,
    low: float,
    high: float,
    *,
    rising: bool,
) -> list[tuple[float, float]]:
    """返回信号从一侧稳定穿越到另一侧的时间区间。"""
    intervals: list[tuple[float, float]] = []
    armed = False
    start: float | None = None
    for index in range(time.size):
        sample = float(values[index])
        if not rising:
            if sample >= high:
                armed = True
            elif armed and sample <= low:
                start = interpolate_crossing(
                    time, values, high, rising=False, end_time_s=float(time[index])
                )
                if start is not None:
                    end = interpolate_crossing(
                        time,
                        values,
                        low,
                        rising=False,
                        start_time_s=start,
                        end_time_s=float(time[index]),
                    )
                    if end is not None and end > start:
                        intervals.append((start, end))
                armed = False
        else:
            if sample <= low:
                armed = True
            elif armed and sample >= high:
                start = interpolate_crossing(
                    time, values, low, rising=True, end_time_s=float(time[index])
                )
                if start is not None:
                    end = interpolate_crossing(
                        time,
                        values,
                        high,
                        rising=True,
                        start_time_s=start,
                        end_time_s=float(time[index]),
                    )
                    if end is not None and end > start:
                        intervals.append((start, end))
                armed = False
    return intervals


def _edge_from_intervals(
    time: np.ndarray,
    values: np.ndarray,
    intervals: list[tuple[float, float]],
    name: str,
    minimum_samples: int,
) -> EdgeTiming:
    if not intervals:
        return EdgeTiming(
            name=name,
            status="NOT_RESOLVED",
            start_time_s=None,
            end_time_s=None,
            duration_s=None,
            sample_count=0,
            max_gap_s=None,
            note="no complete edge found in window",
        )
    durations = np.array([end - start for start, end in intervals], dtype=float)
    mean_duration = float(np.mean(durations))
    counts: list[int] = []
    gaps: list[float] = []
    for start, end in intervals:
        mask = (time >= start) & (time <= end)
        count = int(np.count_nonzero(mask))
        counts.append(count)
        local = time[mask]
        gaps.append(float(np.max(np.diff(local))) if local.size >= 2 else float("inf"))
    mean_count = int(round(float(np.mean(counts))))
    max_gap = float(np.max(gaps))
    resolved = mean_count >= minimum_samples and mean_duration > 0
    return EdgeTiming(
        name=name,
        status="AVAILABLE" if resolved else "NOT_RESOLVED",
        start_time_s=float(intervals[-1][0]),
        end_time_s=float(intervals[-1][1]),
        duration_s=mean_duration,
        sample_count=mean_count,
        max_gap_s=max_gap,
        note=(
            f"averaged over {len(intervals)} edges; min samples per edge={minimum_samples}"
            if resolved
            else f"only {mean_count} samples per edge (< {minimum_samples})"
        ),
    )


def analyze_switching(
    frame: pd.DataFrame,
    *,
    low_ratio: float = 0.1,
    high_ratio: float = 0.9,
    minimum_edge_samples: int = 10,
    switching_frequency_hz: float | None = None,
) -> SwitchingAnalysis:
    """由真实 ``mosfet_vds_v`` / ``mosfet_vgs_v`` 计算边沿、延迟与开关能量。"""
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("frame must be a pandas.DataFrame")
    required = ("time_s", "mosfet_vds_v")
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"switching analysis requires columns: {missing}")
    if not 0.0 <= low_ratio < high_ratio <= 1.0:
        raise ValueError("threshold ratios must satisfy 0 <= low < high <= 1")

    time = frame["time_s"].to_numpy(dtype=float)
    vds = frame["mosfet_vds_v"].to_numpy(dtype=float)
    validate_time_series(time, vds, "mosfet_vds_v")

    vds_low = float(np.percentile(vds, 1.0))
    vds_high = float(np.percentile(vds, 99.0))
    span = vds_high - vds_low
    if span <= 0:
        raise ValueError("VDS has no measurable swing")
    low_threshold = vds_low + low_ratio * span
    high_threshold = vds_low + high_ratio * span

    turn_on_intervals = _transition_intervals(
        time, vds, low_threshold, high_threshold, rising=False
    )
    turn_off_intervals = _transition_intervals(
        time, vds, low_threshold, high_threshold, rising=True
    )
    turn_on = _edge_from_intervals(
        time, vds, turn_on_intervals, "turn_on_vds_fall", minimum_edge_samples
    )
    turn_off = _edge_from_intervals(
        time, vds, turn_off_intervals, "turn_off_vds_rise", minimum_edge_samples
    )

    gate_column = "drive_vgs_command_v"
    if gate_column not in frame.columns:
        gate_column = "mosfet_vgs_v"
    gate = frame[gate_column].to_numpy(dtype=float)
    gate_high = float(np.percentile(gate, 99.0))
    gate_low = float(np.percentile(gate, 1.0))
    gate_mid = gate_low + 0.5 * (gate_high - gate_low)

    turn_on_delay: float | None = None
    turn_off_delay: float | None = None
    if turn_on_intervals:
        command = interpolate_crossing(
            time,
            gate,
            gate_mid,
            rising=True,
            end_time_s=turn_on_intervals[-1][1],
        )
        if command is not None:
            turn_on_delay = float(turn_on_intervals[-1][0] - command)
    if turn_off_intervals:
        command = interpolate_crossing(
            time,
            gate,
            gate_mid,
            rising=False,
            end_time_s=turn_off_intervals[-1][1],
        )
        if command is not None:
            turn_off_delay = float(turn_off_intervals[-1][0] - command)

    cycle_energy: float | None = None
    on_energy: float | None = None
    off_energy: float | None = None
    switching_power: float | None = None
    if "mosfet_drain_terminal_current_a" in frame.columns:
        drain_current = frame["mosfet_drain_terminal_current_a"].to_numpy(dtype=float)
        gate_source = frame["mosfet_vgs_v"].to_numpy(dtype=float)
        gate_span = float(np.percentile(gate_source, 99.0) - np.percentile(gate_source, 1.0))
        if gate_span > 0:
            from .loss_analysis import switching_energy

            energy = switching_energy(
                time,
                vds,
                drain_current,
                gate_source,
                low_level_v=float(np.percentile(gate_source, 1.0)),
                high_level_v=float(np.percentile(gate_source, 99.0)),
            )
            on_count = max(len(energy.turn_on_intervals_s), 1)
            off_count = max(len(energy.turn_off_intervals_s), 1)
            on_energy = float(energy.turn_on_energy_j / on_count)
            off_energy = float(energy.turn_off_energy_j / off_count)
            cycle_energy = float(on_energy + off_energy)
            duration = float(time[-1] - time[0])
            if duration > 0:
                switching_power = float(energy.total_energy_j / duration)

    return SwitchingAnalysis(
        vds_low_v=vds_low,
        vds_high_v=vds_high,
        low_threshold_v=float(low_threshold),
        high_threshold_v=float(high_threshold),
        turn_on=turn_on,
        turn_off=turn_off,
        turn_on_delay_s=turn_on_delay,
        turn_off_delay_s=turn_off_delay,
        edge_count=len(turn_on_intervals),
        cycle_energy_j=cycle_energy,
        turn_on_energy_j=on_energy,
        turn_off_energy_j=off_energy,
        switching_power_w=switching_power,
    )


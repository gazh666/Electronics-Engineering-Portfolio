"""启动过程指标：延迟、上升时间、超调、调节时间、峰值电流与饱和时间。"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from circuits.validators import finite_number, positive_number

from .transient_metrics import cycle_mean_waveform


def _first_crossing(time: np.ndarray, values: np.ndarray, level: float) -> float:
    mask = values >= level
    if not np.any(mask):
        return math.nan
    return float(time[int(np.argmax(mask))])


def _settling_time(
    time: np.ndarray,
    values: np.ndarray,
    *,
    target: float,
    tolerance: float,
    hold_time: float,
) -> tuple[float, str]:
    """返回首次进入并保持容差带的时刻。"""
    inside = np.abs(values - target) <= tolerance
    index = 0
    while index < time.size:
        if not inside[index]:
            index += 1
            continue
        deadline = time[index] + hold_time
        if deadline > time[-1]:
            return math.nan, "INSUFFICIENT_DATA"
        window = (time >= time[index]) & (time <= deadline)
        if np.all(inside[window]):
            return float(time[index]), "OK"
        bad = np.where(~inside[window])[0]
        if bad.size == 0:
            return float(time[index]), "OK"
        index += int(bad[-1]) + 1
    return math.nan, "NOT_SETTLED"


def analyze_startup(
    time_s: Iterable[float],
    voltage_v: Iterable[float],
    reference_v: Iterable[float],
    inductor_current_a: Iterable[float] | None = None,
    input_current_a: Iterable[float] | None = None,
    *,
    target_v: float,
    period_s: float,
    tolerance_v: float | None = None,
    duty_raw: Iterable[float] | None = None,
    duty_limited: Iterable[float] | None = None,
    hold_cycles: int = 20,
    data_source: str = "spice_simulation",
) -> dict[str, Any]:
    """分析软启动或直接启动过程。"""
    time = np.asarray(list(time_s), dtype=float)
    voltage = np.asarray(list(voltage_v), dtype=float)
    reference = np.asarray(list(reference_v), dtype=float)
    if not (time.size == voltage.size == reference.size) or time.size < 3:
        raise ValueError("time, voltage and reference must have equal length (>= 3)")
    if np.any(np.diff(time) <= 0):
        raise ValueError("time must be strictly increasing")
    target = positive_number(target_v, "target_v")
    period = positive_number(period_s, "period_s")
    tolerance = positive_number(
        tolerance_v if tolerance_v is not None else 0.02 * target, "tolerance_v"
    )
    finite = np.isfinite(voltage)

    vref_start = _first_crossing(time, reference, 0.01 * target)
    delay = _first_crossing(time, voltage, 0.10 * target)
    rise_start = delay
    rise_end = _first_crossing(time, voltage, 0.90 * target)
    rise_time = rise_end - rise_start if math.isfinite(rise_start) and math.isfinite(rise_end) else math.nan
    first_target = _first_crossing(time, voltage, target)

    peak_index = int(np.argmax(np.where(finite, voltage, -np.inf)))
    peak = float(voltage[peak_index]) if finite.any() else math.nan
    overshoot = 100.0 * (peak - target) / target if math.isfinite(peak) else math.nan
    maximum_deviation = peak - target if math.isfinite(peak) else math.nan

    centers, means = cycle_mean_waveform(time, voltage, period)
    if centers.size >= 2:
        settling_time, settling_status = _settling_time(
            centers, means, target=target, tolerance=tolerance,
            hold_time=hold_cycles * period,
        )
        # 以周期均值判定，但把时间平移回周期中心点。
    else:
        settling_time, settling_status = math.nan, "INSUFFICIENT_DATA"

    raw_settle, raw_status = _settling_time(
        time, np.where(finite, voltage, 0.0), target=target, tolerance=tolerance,
        hold_time=hold_cycles * period,
    )

    result: dict[str, Any] = {
        "data_source": data_source,
        "target_v": target,
        "tolerance_v": tolerance,
        "period_s": period,
        "hold_cycles": hold_cycles,
        "reference_rise_start_s": vref_start,
        "output_delay_s": delay,
        "rise_start_s": rise_start,
        "rise_end_s": rise_end,
        "rise_time_s": rise_time,
        "first_target_crossing_s": first_target,
        "peak_voltage_v": peak,
        "peak_time_s": float(time[peak_index]) if finite.any() else math.nan,
        "overshoot_v": maximum_deviation,
        "overshoot_percent": overshoot,
        "settling_time_s": settling_time,
        "settling_status": settling_status,
        "raw_settling_time_s": raw_settle,
        "raw_settling_status": raw_status,
        "maximum_deviation_v": maximum_deviation,
        "final_mean_v": math.nan,
        "steady_state_error_v": math.nan,
        "peak_inductor_current_a": math.nan,
        "peak_input_current_a": math.nan,
        "duty_saturation_time_s": 0.0,
        "duty_saturation_fraction": 0.0,
        "status": "OK" if finite.all() else "NONFINITE_SAMPLES",
    }
    tail = cycle_mean_waveform(time, voltage, period, start_s=max(0.0, time[-1] - max(10.0 * period, 0.2 * time[-1])))
    if tail[1].size:
        final_mean = float(np.mean(tail[1]))
        result["final_mean_v"] = final_mean
        result["steady_state_error_v"] = final_mean - target

    if inductor_current_a is not None:
        current = np.asarray(list(inductor_current_a), dtype=float)
        if current.size == time.size:
            result["peak_inductor_current_a"] = float(np.nanmax(current))
    if input_current_a is not None:
        current = np.asarray(list(input_current_a), dtype=float)
        if current.size == time.size:
            result["peak_input_current_a"] = float(np.nanmax(current))
    if duty_raw is not None and duty_limited is not None:
        raw = np.asarray(list(duty_raw), dtype=float)
        limited = np.asarray(list(duty_limited), dtype=float)
        if raw.size == time.size == limited.size:
            saturated = np.abs(raw - limited) > 1e-9
            duration = float(np.sum(np.diff(time) * saturated[:-1])) if time.size > 1 else 0.0
            result["duty_saturation_time_s"] = duration
            result["duty_saturation_fraction"] = duration / float(time[-1] - time[0])
    return result


__all__ = ["analyze_startup"]

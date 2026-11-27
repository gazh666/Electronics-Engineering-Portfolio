"""电池脉冲响应指标提取。

所有指标均来自实际波形列，不假设理想数值；无法确定恢复时标记 NOT_RECOVERED。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


class PulseAnalysisError(ValueError):
    """波形或时间点非法。"""


def _nearest_index(times: np.ndarray, target: float) -> int:
    return int(np.argmin(np.abs(times - target)))


def _window_mean(frame: pd.DataFrame, start_s: float, end_s: float, column: str) -> float:
    mask = (frame["time_s"] >= start_s) & (frame["time_s"] < end_s - 1e-12)
    if not mask.any():
        raise PulseAnalysisError(f"[{start_s}, {end_s}) 区间没有采样点")
    return float(frame.loc[mask, column].mean())


def analyze_pulse(
    frame: pd.DataFrame,
    *,
    step_time_s: float,
    release_time_s: float,
    tolerance_v: float = 0.001,
    observation_window_s: float = 60.0,
    hold_time_s: float = 1.0,
    baseline_window_s: float = 5.0,
    data_source: str = "custom_ecm_simulation",
) -> dict[str, Any]:
    """提取负载接入/断开指标与欧姆内阻估计。

    恢复判定口径：目标参考电压为负载接入前的平均端电压，
    容差 ``tolerance_v``，连续保持 ``hold_time_s``，观察窗口 ``observation_window_s``。
    """
    for column in ("time_s", "current_a", "terminal_voltage_v"):
        if column not in frame.columns:
            raise PulseAnalysisError(f"波形缺少列: {column}")
    if not (frame["time_s"].iloc[0] <= step_time_s < release_time_s <= frame["time_s"].iloc[-1]):
        raise PulseAnalysisError("时间点必须位于波形范围内且 step < release")
    if tolerance_v <= 0 or observation_window_s <= 0:
        raise PulseAnalysisError("容差与观察窗口必须为正")

    times = frame["time_s"].to_numpy(dtype=float)
    voltages = frame["terminal_voltage_v"].to_numpy(dtype=float)
    currents = frame["current_a"].to_numpy(dtype=float)

    pre_step_voltage = _window_mean(frame, step_time_s - baseline_window_s, step_time_s, "terminal_voltage_v")
    step_index = int(np.searchsorted(times, step_time_s - 1e-12, side="left"))
    release_index = int(np.searchsorted(times, release_time_s - 1e-12, side="left"))
    if step_index >= times.size or release_index <= 0:
        raise PulseAnalysisError("无法定位接入或断开采样点")

    current_before = float(currents[max(step_index - 1, 0)])
    current_after = float(currents[step_index])
    delta_current = current_after - current_before
    voltage_after_step = float(voltages[step_index])
    instantaneous_drop = pre_step_voltage - voltage_after_step

    end_index = max(release_index - 1, step_index)
    end_of_pulse_voltage = float(voltages[end_index])
    pulse_window = voltages[step_index:release_index]
    max_drop = pre_step_voltage - float(np.min(pulse_window)) if pulse_window.size else instantaneous_drop

    release_pre_voltage = end_of_pulse_voltage
    release_index_effective = int(np.searchsorted(times, release_time_s - 1e-12, side="left"))
    if release_index_effective >= times.size:
        release_index_effective = times.size - 1
    release_post_voltage = float(voltages[release_index_effective])
    recovery_jump = release_post_voltage - release_pre_voltage

    r0_estimate = None
    if abs(delta_current) > 1e-12:
        r0_estimate = instantaneous_drop / delta_current

    reference = pre_step_voltage
    window_end = min(release_time_s + observation_window_s, float(times[-1]))
    mask = (times >= release_time_s) & (times <= window_end)
    window_times = times[mask]
    window_voltages = voltages[mask]
    recovery_time = None
    recovery_status = "NOT_RECOVERED"
    if window_times.size:
        within = np.abs(window_voltages - reference) <= tolerance_v
        if within.any():
            last_failure = None
            for index, flag in enumerate(within):
                if not flag:
                    last_failure = index
            start_index = 0 if last_failure is None else last_failure + 1
            if start_index < window_times.size:
                candidate = float(window_times[start_index] - release_time_s)
                remaining = float(window_times[-1] - window_times[start_index])
                if remaining + 1e-12 >= min(hold_time_s, window_end - release_time_s):
                    recovery_time = candidate
                    recovery_status = "RECOVERED"

    return {
        "step_time_s": float(step_time_s),
        "release_time_s": float(release_time_s),
        "pre_step_voltage_v": pre_step_voltage,
        "current_before_a": current_before,
        "current_after_a": current_after,
        "delta_current_a": delta_current,
        "instantaneous_voltage_after_step_v": voltage_after_step,
        "instantaneous_drop_v": instantaneous_drop,
        "max_drop_v": max_drop,
        "end_of_pulse_voltage_v": end_of_pulse_voltage,
        "release_pre_voltage_v": release_pre_voltage,
        "release_post_voltage_v": release_post_voltage,
        "recovery_jump_v": recovery_jump,
        "r0_estimate_ohm": r0_estimate,
        "recovery_reference_v": reference,
        "recovery_tolerance_v": float(tolerance_v),
        "recovery_hold_time_s": float(hold_time_s),
        "recovery_observation_window_s": float(observation_window_s),
        "recovery_observed_end_s": float(window_end),
        "recovery_time_s": recovery_time,
        "recovery_status": recovery_status,
        "data_source": data_source,
    }

"""保护联动辅助：生成保护控制时序并从真实波形提取分级时间指标。

必须区分的五个时刻：

- ``fault_start_time_s``：故障/控制信号开始变化；
- ``fet_command_off_time_s``：保护控制信号降到阈值以下；
- ``battery_current_suppressed_time_s``：电池电流降到故障前 5% 以内；
- ``converter_input_voltage_decay_time_s``：Buck 输入低于有效工作下限；
- ``output_voltage_below_limit_time_s``：输出低于工程稳压下限。

这不是"保护响应时间"的单一数字。
"""

from __future__ import annotations

import numpy as np


def protection_control_points(
    fault_time_s: float,
    end_time_s: float,
    *,
    fall_time_s: float = 10e-6,
    pre_fault_voltage: float = 1.0,
) -> list[tuple[float, float]]:
    """控制信号 1 → 0 的 PWL 点列（1=导通，0=关断）。"""
    if fault_time_s <= 0 or fault_time_s >= end_time_s:
        raise ValueError("故障时刻必须位于仿真窗口内部")
    if fall_time_s <= 0:
        raise ValueError("关断过渡时间必须为正")
    return [
        (0.0, pre_fault_voltage),
        (fault_time_s, pre_fault_voltage),
        (fault_time_s + fall_time_s, 0.0),
        (end_time_s, 0.0),
    ]


def _first_crossing(time: np.ndarray, values: np.ndarray, threshold: float, comparator: str, start_index: int = 0) -> float | None:
    for index in range(max(start_index, 0), len(time)):
        value = values[index]
        if comparator == "below" and value < threshold:
            return float(time[index])
        if comparator == "above" and value > threshold:
            return float(time[index])
    return None


def extract_protection_timing(
    *,
    time_s,
    battery_current_a,
    battery_voltage_v,
    converter_input_voltage_v,
    output_voltage_v,
    fault_start_time_s: float,
    control_off_time_s: float,
    current_ratio: float = 0.05,
    converter_input_min_v: float = 8.5,
    output_voltage_min_v: float = 4.5,
) -> dict[str, float | None]:
    time = np.asarray(time_s, dtype=float)
    current = np.asarray(battery_current_a, dtype=float)
    vin = np.asarray(converter_input_voltage_v, dtype=float)
    vout = np.asarray(output_voltage_v, dtype=float)
    if time.ndim != 1 or any(array.shape != time.shape for array in (current, vin, vout)):
        raise ValueError("波形长度必须一致")
    if not np.isfinite(time).all():
        raise ValueError("时间轴非法")

    pre_mask = (time >= fault_start_time_s * 0.6) & (time < fault_start_time_s)
    if pre_mask.sum() < 5:
        raise ValueError("故障前样本不足")
    pre_current = float(np.mean(current[pre_mask]))
    threshold = abs(pre_current) * current_ratio

    start_index = int(np.searchsorted(time, fault_start_time_s))
    suppressed = _first_crossing(time, np.abs(current), threshold, "below", start_index)
    vin_decay = _first_crossing(time, vin, converter_input_min_v, "below", start_index)
    vout_limit = _first_crossing(time, vout, output_voltage_min_v, "below", start_index)

    def elapsed(moment: float | None, reference: float) -> float | None:
        return None if moment is None else moment - reference

    return {
        "pre_fault_battery_current_a": pre_current,
        "current_suppression_threshold_a": threshold,
        "fault_start_time_s": fault_start_time_s,
        "fet_command_off_time_s": control_off_time_s,
        "battery_current_suppressed_time_s": suppressed,
        "converter_input_voltage_decay_time_s": vin_decay,
        "output_voltage_below_limit_time_s": vout_limit,
        "current_suppression_delay_from_fault_s": elapsed(suppressed, fault_start_time_s),
        "current_suppression_delay_from_command_s": elapsed(suppressed, control_off_time_s),
        "vin_decay_delay_from_command_s": elapsed(vin_decay, control_off_time_s),
        "output_hold_time_s": elapsed(vout_limit, control_off_time_s),
        "min_battery_voltage_v": float(np.min(np.asarray(battery_voltage_v, dtype=float))),
    }


def capacitor_hold_time_s(capacitance_f: float, initial_v: float, final_v: float, power_w: float) -> float | None:
    """理想电容恒功率放电维持时间 t = C(Vi² - Vf²)/(2P)。"""
    if capacitance_f <= 0 or power_w <= 0:
        return None
    if initial_v <= final_v:
        return 0.0
    return capacitance_f * (initial_v**2 - final_v**2) / (2.0 * power_w)


__all__ = ["capacitor_hold_time_s", "extract_protection_timing", "protection_control_points"]

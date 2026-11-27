"""稳态窗口识别、时间加权指标与能量平衡检查。

Buck 启动过程具有明显瞬态，直接对整段波形求纹波会把启动变化当成开关纹波。
本模块先根据真实 PWM 上升沿切分完整开关周期，再比较仿真后段两个相邻窗口的
平均电压、平均电感电流与周期纹波，满足项目预设条件后才标记 ``STEADY_STATE``。

所有平均值使用时间积分 ``Mean(x) = ∫x dt / ∫dt``，以适配 ngspice 非均匀采样。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from circuits.buck_config import SteadyStateConfig
from circuits.validators import finite_number, positive_number

STATUS_STEADY_STATE = "STEADY_STATE"
STATUS_NOT_SETTLED = "NOT_SETTLED"
STATUS_INSUFFICIENT_CYCLES = "INSUFFICIENT_CYCLES"
STATUS_INVALID_WAVEFORM = "INVALID_WAVEFORM"


def _integrate(values: np.ndarray, time: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(values, time))
    return float(np.trapz(values, time))  # pragma: no cover - NumPy < 2


def _time_series(time_s: Any, values: Any, name: str = "values") -> tuple[np.ndarray, np.ndarray]:
    time = np.asarray(time_s, dtype=float)
    array = np.asarray(values, dtype=float)
    if time.ndim != 1 or time.size < 2:
        raise ValueError("time_s must be a 1D array with at least two samples")
    if array.ndim != 1 or array.size != time.size:
        raise ValueError(f"{name} must be a 1D array with the same length as time_s")
    if not np.isfinite(time).all():
        raise ValueError("time_s contains NaN or Infinity")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains NaN or Infinity")
    if not np.all(np.diff(time) > 0):
        raise ValueError("time_s must be strictly increasing")
    return time, array


def time_weighted_mean(time_s: Any, values: Any) -> float:
    """时间加权平均值（梯形积分）。"""
    time, array = _time_series(time_s, values)
    duration = float(time[-1] - time[0])
    if duration <= 0:
        raise ValueError("time span must be positive")
    return _integrate(array, time) / duration


def peak_to_peak(values: Any) -> float:
    """峰峰值 ``max - min``。"""
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        raise ValueError("values must not be empty")
    if not np.isfinite(array).all():
        raise ValueError("values contains NaN or Infinity")
    return float(array.max() - array.min())


def slice_window(
    time_s: Any,
    values: Any,
    start_s: float,
    end_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """截取时间窗口，并在边界处线性插值补点。

    返回的数组首尾时间精确等于 ``start_s`` / ``end_s``（受记录范围限制），
    保证积分区间与所选周期一致。
    """
    time, array = _time_series(time_s, values)
    start = finite_number(start_s, "start_s")
    end = finite_number(end_s, "end_s")
    if end <= start:
        raise ValueError("end_s must be greater than start_s")

    tolerance = max(1e-15, abs(time[-1] - time[0]) * 1e-12)
    if start < time[0] - tolerance or end > time[-1] + tolerance:
        raise ValueError("requested window exceeds the recorded time range")
    start = max(start, float(time[0]))
    end = min(end, float(time[-1]))

    mask = (time > start) & (time < end)
    inner_time = time[mask]
    inner_values = array[mask]
    if inner_time.size == 0:
        raise ValueError("window contains no interior samples")

    boundary_time = np.concatenate(([start], inner_time, [end]))
    boundary_values = np.concatenate(
        (
            [np.interp(start, time, array)],
            inner_values,
            [np.interp(end, time, array)],
        )
    )
    if boundary_time.size < 2:
        raise ValueError("window needs at least two samples")
    return boundary_time, boundary_values


def cycle_ripples(
    time_s: Any,
    values: Any,
    boundaries_s: Any,
) -> list[float]:
    """逐周期峰峰值列表；``boundaries_s`` 为每个周期的起止时间。"""
    time, array = _time_series(time_s, values)
    boundaries = np.asarray(boundaries_s, dtype=float)
    if boundaries.ndim != 1 or boundaries.size < 2:
        raise ValueError("boundaries_s needs at least two times")
    if not np.isfinite(boundaries).all() or not np.all(np.diff(boundaries) > 0):
        raise ValueError("boundaries_s must be finite and strictly increasing")

    ripples: list[float] = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        _, window = slice_window(time, array, float(start), float(end))
        ripples.append(float(window.max() - window.min()))
    return ripples


@dataclass(frozen=True)
class SteadyStateWindow:
    """稳态窗口判定结果。"""

    start_time_s: float
    end_time_s: float
    complete_cycles: int
    voltage_mean_change_ratio: float
    current_mean_change_ratio: float
    ripple_change_ratio: float
    status: str
    mean_output_voltage_v: float = math.nan
    mean_inductor_current_a: float = math.nan
    note: str = ""

    @property
    def is_steady(self) -> bool:
        return self.status == STATUS_STEADY_STATE

    def to_dict(self) -> dict[str, Any]:
        def _clean(value: float) -> float | None:
            return None if not math.isfinite(value) else float(value)

        return {
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "complete_cycles": self.complete_cycles,
            "voltage_mean_change_ratio": _clean(self.voltage_mean_change_ratio),
            "current_mean_change_ratio": _clean(self.current_mean_change_ratio),
            "ripple_change_ratio": _clean(self.ripple_change_ratio),
            "status": self.status,
            "mean_output_voltage_v": _clean(self.mean_output_voltage_v),
            "mean_inductor_current_a": _clean(self.mean_inductor_current_a),
            "note": self.note,
        }


def _relative_change(first: float, second: float, absolute_scale: float) -> float:
    scale = max(abs(first), abs(absolute_scale))
    if scale <= 0:
        return math.inf
    return abs(second - first) / scale


def identify_steady_state(
    time_s: Any,
    output_voltage_v: Any,
    inductor_current_a: Any,
    cycle_boundaries_s: Any,
    config: SteadyStateConfig | None = None,
) -> SteadyStateWindow:
    """识别稳态窗口。

    只使用完整开关周期；从最后 ``2 * comparison_cycles`` 个周期中
    比较前后两半的平均值、纹波变化与长期漂移。
    """
    config = config or SteadyStateConfig()
    if not isinstance(config, SteadyStateConfig):
        raise ValueError("config must be SteadyStateConfig")
    time, output = _time_series(time_s, output_voltage_v, "output_voltage_v")
    _, current = _time_series(time_s, inductor_current_a, "inductor_current_a")

    boundaries = np.asarray(cycle_boundaries_s, dtype=float)
    if boundaries.ndim != 1 or boundaries.size < 2:
        raise ValueError("at least one complete switching cycle is required")
    if not np.isfinite(boundaries).all() or not np.all(np.diff(boundaries) > 0):
        raise ValueError("cycle boundaries must be finite and strictly increasing")

    tolerance = max(1e-15, (time[-1] - time[0]) * 1e-9)
    usable = boundaries[(boundaries >= time[0] - tolerance) & (boundaries <= time[-1] + tolerance)]
    if usable.size < 2:
        return SteadyStateWindow(
            start_time_s=float(time[0]),
            end_time_s=float(time[-1]),
            complete_cycles=0,
            voltage_mean_change_ratio=math.nan,
            current_mean_change_ratio=math.nan,
            ripple_change_ratio=math.nan,
            status=STATUS_INSUFFICIENT_CYCLES,
            note="no complete switching cycle inside the recorded waveform",
        )

    available = usable.size - 1
    required = max(config.minimum_cycles, 2 * config.comparison_cycles)
    if available < required:
        return SteadyStateWindow(
            start_time_s=float(usable[0]),
            end_time_s=float(usable[-1]),
            complete_cycles=int(available),
            voltage_mean_change_ratio=math.nan,
            current_mean_change_ratio=math.nan,
            ripple_change_ratio=math.nan,
            status=STATUS_INSUFFICIENT_CYCLES,
            note=f"need {required} complete cycles, only {available} available",
        )

    comparison = config.comparison_cycles
    window_boundaries = usable[-(2 * comparison + 1):]
    split_index = comparison
    first_boundaries = window_boundaries[: split_index + 1]
    second_boundaries = window_boundaries[split_index:]

    try:
        first_time, first_output = slice_window(
            time, output, float(first_boundaries[0]), float(first_boundaries[-1])
        )
        second_time, second_output = slice_window(
            time, output, float(second_boundaries[0]), float(second_boundaries[-1])
        )
        _, first_current = slice_window(
            time, current, float(first_boundaries[0]), float(first_boundaries[-1])
        )
        _, second_current = slice_window(
            time, current, float(second_boundaries[0]), float(second_boundaries[-1])
        )
    except ValueError as exc:
        return SteadyStateWindow(
            start_time_s=float(window_boundaries[0]),
            end_time_s=float(window_boundaries[-1]),
            complete_cycles=int(2 * comparison),
            voltage_mean_change_ratio=math.nan,
            current_mean_change_ratio=math.nan,
            ripple_change_ratio=math.nan,
            status=STATUS_INVALID_WAVEFORM,
            note=str(exc),
        )

    first_voltage_mean = time_weighted_mean(first_time, first_output)
    second_voltage_mean = time_weighted_mean(second_time, second_output)
    first_current_mean = time_weighted_mean(first_time, first_current)
    second_current_mean = time_weighted_mean(second_time, second_current)

    first_ripples = cycle_ripples(time, output, first_boundaries)
    second_ripples = cycle_ripples(time, output, second_boundaries)
    first_ripple = float(np.mean(first_ripples))
    second_ripple = float(np.mean(second_ripples))

    voltage_change = _relative_change(
        first_voltage_mean, second_voltage_mean, config.absolute_voltage_tolerance_v
    )
    current_change = _relative_change(
        first_current_mean, second_current_mean, config.absolute_current_tolerance_a
    )
    ripple_change = _relative_change(
        first_ripple, second_ripple, config.absolute_ripple_tolerance_v
    )

    steady = (
        voltage_change <= config.relative_mean_tolerance
        and current_change <= config.relative_mean_tolerance
        and ripple_change <= config.ripple_relative_tolerance
    )

    return SteadyStateWindow(
        start_time_s=float(window_boundaries[0]),
        end_time_s=float(window_boundaries[-1]),
        complete_cycles=int(2 * comparison),
        voltage_mean_change_ratio=float(voltage_change),
        current_mean_change_ratio=float(current_change),
        ripple_change_ratio=float(ripple_change),
        status=STATUS_STEADY_STATE if steady else STATUS_NOT_SETTLED,
        mean_output_voltage_v=float(second_voltage_mean),
        mean_inductor_current_a=float(second_current_mean),
        note=(
            "last two adjacent cycle groups compared"
            if steady
            else "adjacent cycle groups differ beyond the configured tolerances"
        ),
    )


def steady_state_metrics(
    time_s: Any,
    waveforms: Mapping[str, Any],
    window: SteadyStateWindow,
    cycle_boundaries_s: Any,
) -> dict[str, Any]:
    """基于稳态完整周期计算基础指标（时间加权）。"""
    if not isinstance(window, SteadyStateWindow):
        raise ValueError("window must be SteadyStateWindow")
    if not isinstance(waveforms, Mapping):
        raise ValueError("waveforms must be a mapping of name -> array")
    required = ("vout_v", "inductor_current_a", "input_current_a", "load_current_a")
    missing = [name for name in required if name not in waveforms]
    if missing:
        raise ValueError(f"missing waveform fields: {missing}")

    time = np.asarray(time_s, dtype=float)
    sliced: dict[str, np.ndarray] = {}
    for name in required:
        sliced_time, values = slice_window(time, waveforms[name], window.start_time_s, window.end_time_s)
        sliced[name] = values
    time_window = sliced_time

    boundaries = np.asarray(cycle_boundaries_s, dtype=float)
    inside = boundaries[
        (boundaries >= window.start_time_s - 1e-15) & (boundaries <= window.end_time_s + 1e-15)
    ]
    if inside.size < 2:
        raise ValueError("no complete cycle boundaries inside the steady-state window")

    vout = sliced["vout_v"]
    current = sliced["inductor_current_a"]
    output_ripples = cycle_ripples(time, waveforms["vout_v"], inside)
    current_ripples = cycle_ripples(time, waveforms["inductor_current_a"], inside)

    return {
        "window_start_s": window.start_time_s,
        "window_end_s": window.end_time_s,
        "complete_cycles": int(inside.size - 1),
        "output_voltage_mean_v": time_weighted_mean(time_window, vout),
        "output_voltage_max_v": float(vout.max()),
        "output_voltage_min_v": float(vout.min()),
        "output_voltage_ripple_vpp": peak_to_peak(vout),
        "inductor_current_mean_a": time_weighted_mean(time_window, current),
        "inductor_current_peak_a": float(current.max()),
        "inductor_current_valley_a": float(current.min()),
        "inductor_current_ripple_app": peak_to_peak(current),
        "input_current_mean_a": time_weighted_mean(time_window, sliced["input_current_a"]),
        "load_current_mean_a": time_weighted_mean(time_window, sliced["load_current_a"]),
        "per_cycle_output_ripple_vpp": output_ripples,
        "per_cycle_inductor_ripple_app": current_ripples,
        "output_ripple_std_v": float(np.std(output_ripples)),
        "inductor_ripple_std_a": float(np.std(current_ripples)),
        "data_source": "spice_simulation",
    }


def inductor_volt_second_balance(
    time_s: Any,
    inductor_voltage_v: Any,
    inductor_current_a: Any,
    inductance_h: float,
    window: SteadyStateWindow,
) -> dict[str, Any]:
    """电感伏秒平衡：``∫VL dt`` 与 ``L * ΔIL`` 对比。"""
    inductance = positive_number(inductance_h, "inductance_h")
    if not isinstance(window, SteadyStateWindow):
        raise ValueError("window must be SteadyStateWindow")

    time = np.asarray(time_s, dtype=float)
    window_time, voltage = slice_window(
        time, inductor_voltage_v, window.start_time_s, window.end_time_s
    )
    _, current = slice_window(
        time, inductor_current_a, window.start_time_s, window.end_time_s
    )
    integral = _integrate(voltage, window_time)
    current_change = float(current[-1] - current[0])
    expected = inductance * current_change
    difference = integral - expected
    scale = inductance * peak_to_peak(current)
    relative = abs(difference) / scale if scale > 0 else None

    return {
        "integral_vl_dt_v_s": float(integral),
        "inductor_delta_current_a": current_change,
        "expected_l_delta_i_v_s": float(expected),
        "difference_v_s": float(difference),
        "relative_error": None if relative is None else float(relative),
        "window_start_s": window.start_time_s,
        "window_end_s": window.end_time_s,
        "inductance_h": inductance,
        "data_source": "spice_simulation",
        "note": "VL = V(lx) - V(out); integral(VL dt) should equal L * (IL_end - IL_start)",
    }


def capacitor_charge_balance(
    time_s: Any,
    capacitor_current_a: Any,
    output_voltage_v: Any,
    capacitance_f: float,
    window: SteadyStateWindow,
) -> dict[str, Any]:
    """电容电荷平衡：``∫IC dt`` 与 ``C * ΔVout`` 对比。

    ``IC`` 由 ``IL - Iload`` 派生，因此该检查含有一部分 KCL 自洽关系，
    不是完全独立的电流测量验证。
    """
    capacitance = positive_number(capacitance_f, "capacitance_f")
    if not isinstance(window, SteadyStateWindow):
        raise ValueError("window must be SteadyStateWindow")

    time = np.asarray(time_s, dtype=float)
    window_time, current = slice_window(
        time, capacitor_current_a, window.start_time_s, window.end_time_s
    )
    _, voltage = slice_window(
        time, output_voltage_v, window.start_time_s, window.end_time_s
    )
    integral = _integrate(current, window_time)
    voltage_change = float(voltage[-1] - voltage[0])
    expected = capacitance * voltage_change
    difference = integral - expected
    scale = capacitance * peak_to_peak(voltage)
    relative = abs(difference) / scale if scale > 0 else None

    return {
        "integral_ic_dt_c": float(integral),
        "output_voltage_delta_v": voltage_change,
        "expected_c_delta_v_c": float(expected),
        "difference_c": float(difference),
        "relative_error": None if relative is None else float(relative),
        "window_start_s": window.start_time_s,
        "window_end_s": window.end_time_s,
        "capacitance_f": capacitance,
        "data_source": "spice_simulation",
        "note": "IC is a KCL-derived quantity (IL - Iload), not an independent current measurement",
    }


def settling_time_s(
    time_s: Any,
    values: Any,
    reference: float,
    *,
    relative_band: float = 0.02,
    absolute_band: float = 0.01,
    minimum_hold_s: float = 5e-4,
) -> float | None:
    """启动稳定时间；无法确认时返回 ``None``（输出 NOT_SETTLED）。

    稳定判定：从某时刻起，输出始终处于 ``reference ± max(abs, rel*|ref|)``
    之内，且该状态持续不少于 ``minimum_hold_s``。
    """
    time, array = _time_series(time_s, values)
    reference = finite_number(reference, "reference")
    relative = finite_number(relative_band, "relative_band")
    absolute = finite_number(absolute_band, "absolute_band")
    hold = positive_number(minimum_hold_s, "minimum_hold_s")
    if relative < 0 or absolute <= 0:
        raise ValueError("bands must be nonnegative, absolute_band must be positive")

    band = max(absolute, abs(reference) * relative)
    outside = np.abs(array - reference) > band
    if not np.any(outside):
        return float(time[0])
    last_outside = int(np.flatnonzero(outside)[-1])
    if last_outside >= len(time) - 1:
        return None
    candidate = float(time[last_outside + 1])
    if candidate + hold > float(time[-1]):
        return None
    return candidate

"""软启动参考电压：Vref(t) = Vtarget × min(t/Tss, 1)。"""

from __future__ import annotations

import math

from circuits.validators import finite_number


def soft_start_reference(
    time_s: float,
    target_v: float = 5.0,
    duration_s: float = 0.002,
    initial_v: float = 0.0,
    enabled: bool = True,
) -> float:
    """返回给定时刻的参考电压。

    ``duration_s <= 0`` 或 ``enabled=False`` 时立即输出目标电压。
    时间轴为负时返回初始值，不抛错（便于时间插值）。
    """
    time = finite_number(time_s, "time_s")
    target = finite_number(target_v, "target_v")
    initial = finite_number(initial_v, "initial_v")
    duration = finite_number(duration_s, "duration_s")
    if duration < 0:
        raise ValueError("duration_s must be nonnegative")
    if target <= initial:
        raise ValueError("target_v must exceed initial_v")
    if not enabled or duration == 0.0:
        return target
    if time <= 0.0:
        return initial
    ratio = min(time / duration, 1.0)
    value = initial + (target - initial) * ratio
    return max(initial, min(value, target))


def soft_start_points(
    target_v: float,
    duration_s: float,
    *,
    initial_v: float = 0.0,
    end_time_s: float | None = None,
    enabled: bool = True,
) -> list[tuple[float, float]]:
    """构造 SPICE PWL 参考电压点。

    返回 (时间, 电压) 列表，至少包含起点。
    无软启动时使用 0.1 µs 的有限上升，避免 PWL 在 t=0 处与 DC 工作点冲突。
    """
    target = finite_number(target_v, "target_v")
    initial = finite_number(initial_v, "initial_v")
    duration = finite_number(duration_s, "duration_s")
    if duration < 0:
        raise ValueError("duration_s must be nonnegative")
    if end_time_s is not None:
        end = finite_number(end_time_s, "end_time_s")
        if end <= 0:
            raise ValueError("end_time_s must be positive")
    else:
        end = None
    if not enabled or duration == 0.0:
        points = [(0.0, initial), (1e-7, target)]
        if end is not None:
            points.append((max(end, 2e-7), target))
        return points
    points = [(0.0, initial), (duration, target)]
    if end is not None and end > duration:
        points.append((end, target))
    return points


def ramp_rate_v_per_s(target_v: float, duration_s: float) -> float:
    """软启动参考斜率（V/s）；无软启动时返回 ``inf``。"""
    target = finite_number(target_v, "target_v")
    duration = finite_number(duration_s, "duration_s")
    if duration < 0:
        raise ValueError("duration_s must be nonnegative")
    if duration == 0:
        return math.inf
    return target / duration

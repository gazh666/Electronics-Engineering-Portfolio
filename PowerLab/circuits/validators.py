"""统一 SI 单位参数校验。

所有电路构建器、配置加载器与仿真执行器都必须经过本模块，
避免把 NaN / Infinity / 布尔值 / 字符串当成合法参数。

电压类参数允许负值（例如二极管反向偏置、负输入阶跃），
因此本模块只提供 ``finite_number``，是否允许负值由调用方按物理意义选择。
"""

from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Sequence

#: 单次 DC 扫描允许的最大工况点数。
MAX_DC_SWEEP_POINTS = 100_000

#: 单次 AC 扫描允许的最大数据点数。
MAX_AC_SWEEP_POINTS = 200_000

#: 单次瞬态分析允许的最大估算点数（end_time / step_time）。
MAX_TRANSIENT_POINTS = 2_000_000

#: 允许的温度下限（摄氏度，绝对零度）。
MIN_TEMPERATURE_C = -273.15


def finite_number(value: object, name: str) -> float:
    """返回有限浮点数；拒绝布尔值、字符串、NaN、Infinity。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be bool")
    if not isinstance(value, Real):
        raise ValueError(f"{name} must be numeric, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return number


def positive_number(value: object, name: str) -> float:
    """返回严格大于 0 的有限数。"""
    number = finite_number(value, name)
    if number <= 0:
        raise ValueError(f"{name} must be positive, got {value!r}")
    return number


def nonnegative_number(value: object, name: str) -> float:
    """返回大于等于 0 的有限数。"""
    number = finite_number(value, name)
    if number < 0:
        raise ValueError(f"{name} must be nonnegative, got {value!r}")
    return number


def positive_integer(value: object, name: str, *, minimum: int = 1) -> int:
    """返回不小于 ``minimum`` 的整数；拒绝布尔值与浮点表示。"""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer, got {type(value).__name__}")
    number = int(value)
    if number < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value!r}")
    return number


def temperature_celsius(value: object, name: str = "temperature_c") -> float:
    """返回摄氏温度；物理上必须高于绝对零度。"""
    number = finite_number(value, name)
    if number <= MIN_TEMPERATURE_C:
        raise ValueError(f"{name} must be above {MIN_TEMPERATURE_C} C, got {value!r}")
    return number


def dc_sweep(start: object, stop: object, step: object, *, name: str = "dc_sweep") -> tuple[float, float, float]:
    """校验直流扫描参数并返回 ``(start, stop, step)``。

    规则：
    - 起止值必须为有限数且不能相等；
    - 步长必须为非零有限数，符号必须与扫描方向一致；
    - 估计点数不得超过 :data:`MAX_DC_SWEEP_POINTS`。
    """
    start_v = finite_number(start, f"{name}.start")
    stop_v = finite_number(stop, f"{name}.stop")
    step_v = finite_number(step, f"{name}.step")

    if start_v == stop_v:
        raise ValueError(f"{name}.start and {name}.stop must differ")
    if step_v == 0:
        raise ValueError(f"{name}.step must be nonzero")

    ascending = stop_v > start_v
    if ascending and step_v < 0:
        raise ValueError(f"{name}.step must be positive for an ascending sweep")
    if not ascending and step_v > 0:
        raise ValueError(f"{name}.step must be negative for a descending sweep")

    points = int(math.floor((stop_v - start_v) / step_v + 1e-9)) + 1
    if points < 2:
        raise ValueError(f"{name} must produce at least 2 points")
    if points > MAX_DC_SWEEP_POINTS:
        raise ValueError(f"{name} produces {points} points, limit is {MAX_DC_SWEEP_POINTS}")
    return start_v, stop_v, step_v


def transient_parameters(
    step_s: object,
    end_s: object,
    start_s: object = 0.0,
    *,
    name: str = "transient",
) -> tuple[float, float, float]:
    """校验瞬态时间参数并返回 ``(start_s, end_s, step_s)``。"""
    start = nonnegative_number(start_s, f"{name}.start_s")
    end = positive_number(end_s, f"{name}.end_s")
    step = positive_number(step_s, f"{name}.step_s")

    if start >= end:
        raise ValueError(f"{name}.start_s must be less than {name}.end_s")
    if step >= (end - start):
        raise ValueError(f"{name}.step_s must be smaller than the simulated span")

    estimated = int(math.ceil((end - start) / step)) + 1
    if estimated > MAX_TRANSIENT_POINTS:
        raise ValueError(
            f"{name} estimates {estimated} points, limit is {MAX_TRANSIENT_POINTS}"
        )
    return start, end, step


def transient_max_time(max_s: object, step_s: object, *, name: str = "transient") -> float:
    """校验 SPICE ``tmax``（内部最大时间步长）。

    ``tmax`` 必须为正且不得超过输出步长 ``step_s``；否则它无法约束求解器。
    """
    max_time = positive_number(max_s, f"{name}.max_time_s")
    step = positive_number(step_s, f"{name}.step_s")
    if max_time > step:
        raise ValueError(
            f"{name}.max_time_s must not exceed step_s: {max_time!r} > {step!r}"
        )
    return max_time


def ac_sweep(
    start_hz: object,
    stop_hz: object,
    points_per_decade: object = 50,
    *,
    variation: str = "dec",
    name: str = "ac",
) -> tuple[float, float, int, str]:
    """校验 AC 扫描参数并返回 ``(start_hz, stop_hz, points_per_decade, variation)``。"""
    start = positive_number(start_hz, f"{name}.start_hz")
    stop = positive_number(stop_hz, f"{name}.stop_hz")
    points = positive_integer(points_per_decade, f"{name}.points_per_decade", minimum=1)

    if stop <= start:
        raise ValueError(f"{name}.stop_hz must be greater than {name}.start_hz")
    if variation not in ("dec", "oct", "lin"):
        raise ValueError(f"{name}.variation must be dec/oct/lin, got {variation!r}")
    if points > 10_000:
        raise ValueError(f"{name}.points_per_decade is unreasonably large: {points}")

    if variation == "dec":
        decades = math.log10(stop / start)
        estimated = int(math.floor(decades * points)) + 1
    elif variation == "oct":
        octaves = math.log2(stop / start)
        estimated = int(math.floor(octaves * points)) + 1
    else:  # lin：points_per_decade 解释为总点数
        estimated = points
    if estimated > MAX_AC_SWEEP_POINTS:
        raise ValueError(
            f"{name} estimates {estimated} points, limit is {MAX_AC_SWEEP_POINTS}"
        )
    return start, stop, points, variation


def strictly_increasing(values: Sequence[float], name: str) -> None:
    """校验一维序列严格递增。"""
    if len(values) < 2:
        raise ValueError(f"{name} needs at least two samples")
    previous = finite_number(values[0], f"{name}[0]")
    for index in range(1, len(values)):
        current = finite_number(values[index], f"{name}[{index}]")
        if current <= previous:
            raise ValueError(f"{name} must be strictly increasing at index {index}")
        previous = current

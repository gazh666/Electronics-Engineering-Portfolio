"""电池基础性能计算。

内部统一约定：
- 时间：秒；电流：安培；电压：伏特；电阻：欧姆；容量：Ah；能量：Wh；SOC：0-1。
- 放电电流为正，充电电流为负。
- 所有外部数据必须先核查原始符号与时基，再通过本项目函数转换。
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

SECONDS_PER_HOUR = 3600.0


def _trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    """兼容 NumPy 新老版本的梯形积分。"""
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))  # pragma: no cover - 仅旧版 NumPy 使用


def _as_series(values: Iterable[float], name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} 必须是一维数组")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} 含有非有限数值")
    return array


def validate_time_series(time_s: Iterable[float], *others: Iterable[float]) -> tuple[np.ndarray, ...]:
    """校验时间轴与若干同步序列：一维、等长、有限、时间严格递增。"""
    time_array = _as_series(time_s, "time_s")
    if time_array.size < 2:
        raise ValueError("时间序列至少需要 2 个采样点")
    if not np.all(np.diff(time_array) > 0):
        raise ValueError("时间必须严格递增")
    arrays = [time_array]
    for index, other in enumerate(others):
        series = _as_series(other, f"series[{index}]")
        if series.size != time_array.size:
            raise ValueError("数组长度不一致")
        arrays.append(series)
    return tuple(arrays)


def calculate_discharge_capacity_ah(time_s: Iterable[float], current_a: Iterable[float]) -> float:
    """放电容量：integral(max(I,0) dt) / 3600。"""
    time_array, current = validate_time_series(time_s, current_a)
    return _trapezoid(np.maximum(current, 0.0), time_array) / SECONDS_PER_HOUR


def calculate_charge_capacity_ah(time_s: Iterable[float], current_a: Iterable[float]) -> float:
    """充电容量：integral(max(-I,0) dt) / 3600。"""
    time_array, current = validate_time_series(time_s, current_a)
    return _trapezoid(np.maximum(-current, 0.0), time_array) / SECONDS_PER_HOUR


def calculate_discharge_energy_wh(
    time_s: Iterable[float],
    voltage_v: Iterable[float],
    current_a: Iterable[float],
) -> float:
    """放电能量：integral(V * max(I,0) dt) / 3600。"""
    time_array, voltage, current = validate_time_series(time_s, voltage_v, current_a)
    return _trapezoid(voltage * np.maximum(current, 0.0), time_array) / SECONDS_PER_HOUR


def calculate_charge_energy_wh(
    time_s: Iterable[float],
    voltage_v: Iterable[float],
    current_a: Iterable[float],
) -> float:
    """充电能量：integral(V * max(-I,0) dt) / 3600。"""
    time_array, voltage, current = validate_time_series(time_s, voltage_v, current_a)
    return _trapezoid(voltage * np.maximum(-current, 0.0), time_array) / SECONDS_PER_HOUR


def instantaneous_power_w(voltage_v: Iterable[float], current_a: Iterable[float]) -> np.ndarray:
    """瞬时电池功率 P = V * I；正功率表示放电输出。"""
    voltage = _as_series(voltage_v, "voltage_v")
    current = _as_series(current_a, "current_a")
    if voltage.size != current.size:
        raise ValueError("数组长度不一致")
    return voltage * current


def split_sign_capacity_ah(
    time_s: Iterable[float],
    current_a: Iterable[float],
) -> tuple[float, float]:
    """在电流符号穿越处插值截断，分别积分放电与充电容量。

    对于含充放电混合的区间，纯 max(I,0) 会产生重复计数，本函数按线性插值
    找到零穿越点后分段积分，返回 (放电容量, 充电容量)。
    """
    time_array, current = validate_time_series(time_s, current_a)
    discharge = 0.0
    charge = 0.0
    for index in range(time_array.size - 1):
        t0, t1 = float(time_array[index]), float(time_array[index + 1])
        i0, i1 = float(current[index]), float(current[index + 1])
        if i0 == 0.0 and i1 == 0.0:
            continue
        if i0 * i1 >= 0.0:
            integral = (i0 + i1) * 0.5 * (t1 - t0)
            if integral >= 0.0:
                discharge += integral
            else:
                charge += -integral
            continue
        # 存在零穿越：解线性插值 t_cross
        t_cross = t0 + (t1 - t0) * (i0 / (i0 - i1))
        positive_part = (i0 * (t_cross - t0)) * 0.5
        negative_part = (i1 * (t1 - t_cross)) * 0.5
        discharge += max(positive_part, 0.0)
        charge += max(-negative_part, 0.0)
    return discharge / SECONDS_PER_HOUR, charge / SECONDS_PER_HOUR


def average_voltage_v(voltage_v: Iterable[float]) -> float:
    voltage = _as_series(voltage_v, "voltage_v")
    return float(np.mean(voltage))


def average_current_a(current_a: Iterable[float]) -> float:
    current = _as_series(current_a, "current_a")
    return float(np.mean(current))


def convert_current_sign(values: Iterable[float], convention: str) -> np.ndarray:
    """按原始符号约定转换为内部约定（放电为正）。

    convention 可选：
    - ``discharge_positive``：原样返回（已在内部约定）。
    - ``charge_positive``：取反（原始数据充电为正）。
    """
    array = _as_series(values, "current")
    if convention == "discharge_positive":
        return array
    if convention == "charge_positive":
        return -array
    raise ValueError(f"未知电流符号约定: {convention!r}")


def convert_time_to_seconds(values: Iterable[float], unit: str) -> np.ndarray:
    """把原始时间转换为秒。unit 支持 s / ms / min / h。"""
    array = _as_series(values, "time")
    factors = {"s": 1.0, "ms": 0.001, "min": 60.0, "h": 3600.0}
    if unit not in factors:
        raise ValueError(f"未知时间单位: {unit!r}")
    return array * factors[unit]


def derive_soc_from_current(
    time_s: Iterable[float],
    current_a: Iterable[float],
    initial_soc: float,
    capacity_ah: float,
) -> np.ndarray:
    """由电流积分派生 SOC（放电为正，SOC 下降）。"""
    if not 0.0 <= initial_soc <= 1.0:
        raise ValueError("initial_soc 必须在 0-1 之间")
    if capacity_ah <= 0:
        raise ValueError("capacity_ah 必须为正")
    time_array, current = validate_time_series(time_s, current_a)
    delivered = np.concatenate(([0.0], np.cumsum(0.5 * (current[1:] + current[:-1]) * np.diff(time_array))))
    soc = initial_soc - delivered / (capacity_ah * SECONDS_PER_HOUR)
    return np.clip(soc, 0.0, 1.0)


def summarize_measurement(
    time_s: Iterable[float],
    voltage_v: Iterable[float],
    current_a: Iterable[float],
    *,
    capacity_ah: float | None = None,
    initial_soc: float | None = None,
) -> dict[str, float | str | None]:
    """汇总一次充放电测量的关键指标（全部来自输入波形）。"""
    time_array, voltage, current = validate_time_series(time_s, voltage_v, current_a)
    discharge_ah, charge_ah = split_sign_capacity_ah(time_array, current)
    discharge_wh = calculate_discharge_energy_wh(time_array, voltage, current)
    charge_wh = calculate_charge_energy_wh(time_array, voltage, current)
    summary: dict[str, float | str | None] = {
        "points": int(time_array.size),
        "duration_s": float(time_array[-1] - time_array[0]),
        "voltage_start_v": float(voltage[0]),
        "voltage_end_v": float(voltage[-1]),
        "voltage_min_v": float(np.min(voltage)),
        "voltage_max_v": float(np.max(voltage)),
        "current_min_a": float(np.min(current)),
        "current_max_a": float(np.max(current)),
        "mean_voltage_v": float(np.mean(voltage)),
        "mean_current_a": float(np.mean(current)),
        "discharge_capacity_ah": discharge_ah,
        "charge_capacity_ah": charge_ah,
        "discharge_energy_wh": discharge_wh,
        "charge_energy_wh": charge_wh,
        "coulombic_efficiency_pct": None,
        "energy_efficiency_pct": None,
    }
    if charge_ah > 0:
        summary["coulombic_efficiency_pct"] = discharge_ah / charge_ah * 100.0
    if charge_wh > 0:
        summary["energy_efficiency_pct"] = discharge_wh / charge_wh * 100.0
    if capacity_ah is not None and initial_soc is not None and capacity_ah > 0:
        soc = derive_soc_from_current(time_array, current, initial_soc, capacity_ah)
        summary["soc_start"] = float(soc[0])
        summary["soc_end"] = float(soc[-1])
    return summary


def segment_statistics(
    time_s: Sequence[float],
    current_a: Sequence[float],
    min_segment_s: float = 1.0,
) -> list[dict[str, float | str | int]]:
    """按电流方向把连续采样划分成放电/充电/静置段。

    每个采样区间按左端点电流方向归类，再合并同类相邻区间。
    """
    time_array, current = validate_time_series(time_s, current_a)
    interval_labels: list[str] = []
    for value in current[:-1]:
        if value > 1e-9:
            interval_labels.append("discharge")
        elif value < -1e-9:
            interval_labels.append("charge")
        else:
            interval_labels.append("rest")
    segments: list[dict[str, float | str | int]] = []
    start = 0
    for index in range(1, len(interval_labels) + 1):
        if index == len(interval_labels) or interval_labels[index] != interval_labels[start]:
            segments.append(
                {
                    "label": interval_labels[start],
                    "start_s": float(time_array[start]),
                    "end_s": float(time_array[index]),
                    "duration_s": float(time_array[index] - time_array[start]),
                    "points": int(index - start + 1),
                    "mean_current_a": float(np.mean(current[start : index + 1])),
                }
            )
            start = index
    return [segment for segment in segments if float(segment["duration_s"]) >= min_segment_s]

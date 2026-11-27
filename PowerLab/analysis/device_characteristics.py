"""器件特性提取（MOSFET 转移 / 输出 / 截止，二极管正向 / 反向）。

本模块只使用真实扫描数据做插值与拟合，不注入理论曲线。
阈值电压与 RDS(on) 都附带拟合方法与区间，超出测量范围时返回 ``None``
而不是外推成看似精确的数字。
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from circuits.validators import finite_number, positive_number
from simulations.device_runner import (
    diode_data,
    mosfet_output_data,
    mosfet_transfer_data,
)
from simulations.models import SimulationResult


def _fit_r2(x: np.ndarray, y: np.ndarray, slope: float, intercept: float) -> float:
    predicted = slope * x + intercept
    residual = float(np.sum((y - predicted) ** 2))
    total = float(np.sum((y - np.mean(y)) ** 2))
    if total <= 0:
        return 0.0
    return 1.0 - residual / total


def linear_fit(x: Iterable[float], y: Iterable[float]) -> dict[str, float]:
    """最小二乘直线拟合，返回斜率和截距与 R²。"""
    x_array = np.asarray(list(x), dtype=float)
    y_array = np.asarray(list(y), dtype=float)
    if x_array.size < 2 or x_array.size != y_array.size:
        raise ValueError("linear_fit needs at least two paired points")
    if not np.isfinite(x_array).all() or not np.isfinite(y_array).all():
        raise ValueError("linear_fit inputs must be finite")
    slope, intercept = np.polyfit(x_array, y_array, 1)
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(_fit_r2(x_array, y_array, slope, intercept)),
        "points": int(x_array.size),
    }


def interpolate_value(
    target_y: float,
    y_values: Iterable[float],
    x_values: Iterable[float],
    *,
    name: str,
) -> dict[str, Any]:
    """在单调递增的 ``y`` 上插值求 ``x``。

    超出测量范围时不外推，返回 ``value=None``。
    """
    y = np.asarray(list(y_values), dtype=float)
    x = np.asarray(list(x_values), dtype=float)
    if y.size != x.size or y.size < 2:
        raise ValueError(f"{name}: need paired arrays with at least two points")
    order = np.argsort(y)
    y_sorted = y[order]
    x_sorted = x[order]
    if not np.all(np.diff(y_sorted) > 0):
        # 允许重复点：去掉重复 y，保留第一个 x
        unique_mask = np.concatenate(([True], np.diff(y_sorted) > 0))
        y_sorted = y_sorted[unique_mask]
        x_sorted = x_sorted[unique_mask]
    if y_sorted.size < 2:
        return {
            "target": float(target_y),
            "value": None,
            "status": "insufficient_distinct_points",
            "range": [float(y_sorted[0]), float(y_sorted[-1])],
        }
    target = finite_number(target_y, f"{name}.target")
    if target < y_sorted[0] or target > y_sorted[-1]:
        return {
            "target": target,
            "value": None,
            "status": "target_outside_measured_range",
            "range": [float(y_sorted[0]), float(y_sorted[-1])],
        }
    value = float(np.interp(target, y_sorted, x_sorted))
    return {
        "target": target,
        "value": value,
        "status": "ok",
        "range": [float(y_sorted[0]), float(y_sorted[-1])],
        "interpolated": True,
    }


def threshold_from_sqrt_fit(
    vgs_v: Iterable[float],
    id_a: Iterable[float],
    *,
    minimum_fraction: float = 0.02,
    maximum_fraction: float = 0.6,
) -> dict[str, Any]:
    """用饱和区 ``sqrt(ID) ∝ (VGS - VTH)`` 线性拟合提取阈值电压。"""
    vgs = np.asarray(list(vgs_v), dtype=float)
    current = np.asarray(list(id_a), dtype=float)
    if vgs.size != current.size or vgs.size < 4:
        raise ValueError("threshold fit needs at least four paired points")
    maximum = float(np.max(current))
    if maximum <= 0:
        return {"threshold_v": None, "status": "no_positive_current"}
    positive = current > 0
    lower = minimum_fraction * maximum
    upper = maximum_fraction * maximum
    mask = positive & (current >= lower) & (current <= upper)
    if int(mask.sum()) < 3:
        return {
            "threshold_v": None,
            "status": "insufficient_fit_points",
            "points": int(mask.sum()),
        }
    fit = linear_fit(vgs[mask], np.sqrt(current[mask]))
    if fit["slope"] <= 0:
        return {
            "threshold_v": None,
            "status": "non_positive_slope",
            "fit": fit,
        }
    threshold = -fit["intercept"] / fit["slope"]
    return {
        "threshold_v": float(threshold),
        "status": "ok",
        "fit": fit,
        "method": "sqrt(ID) linear fit in saturation over 2%-60% of peak current",
        "points_used": int(mask.sum()),
    }


def extract_transfer_characteristics(result: SimulationResult) -> dict[str, Any]:
    """MOSFET 转移特性摘要。"""
    data = mosfet_transfer_data(result)
    vgs = data["vgs_v"]
    current = data["id_a"]
    maximum = float(np.max(current))
    minimum = float(np.min(current))
    off_mask = np.abs(vgs - np.min(vgs)) < 1e-12
    off_current = float(np.max(np.abs(current[off_mask]))) if off_mask.any() else minimum
    threshold = threshold_from_sqrt_fit(vgs, current)
    ratio = None if abs(off_current) == 0 else maximum / abs(off_current)
    return {
        "device": "mosfet",
        "test": "transfer",
        "vds_v": float(result.metadata.get("test_conditions", {}).get("vds_v")),
        "temperature_c": float(
            result.metadata.get("test_conditions", {}).get("temperature_c")
        ),
        "vgs_min_v": float(np.min(vgs)),
        "vgs_max_v": float(np.max(vgs)),
        "drain_current_max_a": maximum,
        "drain_current_min_a": minimum,
        "off_state_current_a": off_current,
        "on_off_current_ratio": ratio,
        "threshold_estimate_v": threshold.get("threshold_v"),
        "threshold_method": threshold.get("method"),
        "threshold_fit": threshold.get("fit"),
        "threshold_status": threshold["status"],
        "samples": int(vgs.size),
        "data_source": "spice_simulation",
    }


def extract_output_characteristics(result: SimulationResult) -> dict[str, Any]:
    """MOSFET 输出特性摘要与低电压区 RDS(on) 拟合。"""
    data = mosfet_output_data(result)
    vds = data["vds_v"]
    current = data["id_a"]
    vgs = float(np.mean(data["vgs_v"]))
    vds_max = float(np.max(vds))

    low_voltage_limit = min(0.1, 0.1 * vds_max)
    mask = (vds >= 0) & (vds <= low_voltage_limit) & (current > 0)
    if int(mask.sum()) >= 2:
        slope = float(np.sum(vds[mask] * current[mask]) / np.sum(vds[mask] ** 2))
        rds_low = None if slope <= 0 else 1.0 / slope
        fit_points = int(mask.sum())
    else:
        rds_low = None
        fit_points = int(mask.sum())

    return {
        "device": "mosfet",
        "test": "output",
        "vgs_v": vgs,
        "temperature_c": float(
            result.metadata.get("test_conditions", {}).get("temperature_c")
        ),
        "vds_max_v": vds_max,
        "drain_current_max_a": float(np.max(current)),
        "saturation_current_at_max_vds_a": float(current[-1]),
        "rds_on_low_vds_ohm": rds_low,
        "rds_fit_voltage_limit_v": low_voltage_limit,
        "rds_fit_points": fit_points,
        "samples": int(vds.size),
        "data_source": "spice_simulation",
    }


def rds_on_at_current(
    result: SimulationResult,
    target_current_a: float,
) -> dict[str, Any]:
    """在真实输出曲线上插值到目标电流，求有效 ``RDS(on) = VDS / ID``。"""
    data = mosfet_output_data(result)
    target = positive_number(target_current_a, "target_current_a")
    interpolation = interpolate_value(
        target,
        data["id_a"],
        data["vds_v"],
        name="rds_on",
    )
    if interpolation["value"] is None:
        return {
            "target_current_a": target,
            "rds_on_ohm": None,
            "vds_v": None,
            "status": interpolation["status"],
            "measured_current_range_a": interpolation["range"],
            "vgs_v": float(np.mean(data["vgs_v"])),
        }
    vds = float(interpolation["value"])
    return {
        "target_current_a": target,
        "rds_on_ohm": vds / target,
        "vds_v": vds,
        "status": "ok" if vds >= 0 else "negative_vds_check_data",
        "measured_current_range_a": interpolation["range"],
        "vgs_v": float(np.mean(data["vgs_v"])),
    }


def extract_off_state(result: SimulationResult) -> dict[str, Any]:
    """截止状态漏电流摘要。"""
    data = mosfet_output_data(result)
    current = data["id_a"]
    vds = data["vds_v"]
    index = int(np.argmax(vds))
    return {
        "device": "mosfet",
        "test": "off_state",
        "vgs_v": float(np.mean(data["vgs_v"])),
        "vds_at_measurement_v": float(vds[index]),
        "drain_leakage_at_max_vds_a": float(current[index]),
        "max_abs_leakage_a": float(np.max(np.abs(current))),
        "temperature_c": float(
            result.metadata.get("test_conditions", {}).get("temperature_c")
        ),
        "data_source": "spice_simulation",
    }


def extract_diode_forward(
    result: SimulationResult,
    reference_currents_a: Iterable[float],
) -> dict[str, Any]:
    """二极管正向特性：给定电流下的正向压降。"""
    data = diode_data(result)
    voltage = data["vd_v"]
    current = data["id_a"]
    forward_mask = current > 0
    if not np.any(forward_mask):
        return {
            "device": "diode",
            "test": "forward",
            "status": "no_forward_current",
        }
    voltage = voltage[forward_mask]
    current = current[forward_mask]
    drops: dict[str, Any] = {}
    for target in reference_currents_a:
        target_value = positive_number(target, "reference_current")
        interpolation = interpolate_value(
            target_value, current, voltage, name=f"diode_vf_{target_value:g}a"
        )
        drops[f"{target_value:g}"] = {
            "current_a": target_value,
            "forward_voltage_v": interpolation["value"],
            "status": interpolation["status"],
        }
    return {
        "device": "diode",
        "test": "forward",
        "temperature_c": float(
            result.metadata.get("test_conditions", {}).get("temperature_c")
        ),
        "forward_current_max_a": float(np.max(current)),
        "forward_voltage_at_max_current_v": float(voltage[np.argmax(current)]),
        "forward_voltage_min_v": float(np.min(voltage)),
        "voltage_drops": drops,
        "samples": int(current.size),
        "data_source": "spice_simulation",
    }


def extract_diode_reverse(result: SimulationResult) -> dict[str, Any]:
    """二极管反向漏电流摘要。"""
    data = diode_data(result)
    voltage = data["vd_v"]
    current = data["id_a"]
    index = int(np.argmin(voltage))
    return {
        "device": "diode",
        "test": "reverse",
        "temperature_c": float(
            result.metadata.get("test_conditions", {}).get("temperature_c")
        ),
        "reverse_voltage_min_v": float(voltage[index]),
        "leakage_at_min_voltage_a": float(current[index]),
        "max_abs_leakage_a": float(np.max(np.abs(current))),
        "samples": int(voltage.size),
        "data_source": "spice_simulation",
    }


def check_device_limits(
    *,
    transfer: dict[str, Any],
    rds: dict[str, Any],
    off_state: dict[str, Any],
    diode_forward: dict[str, Any],
    diode_reverse: dict[str, Any],
    limits: dict[str, Any],
) -> dict[str, Any]:
    """按 ``nonideal_validation.yaml`` 的器件判据给出检查结果。"""
    device = limits.get("device", {})
    required = (
        "off_state_current_ratio_max",
        "rds_on_min_ohm",
        "rds_on_max_ohm",
        "diode_forward_drop_min_v",
        "diode_forward_drop_max_v",
        "diode_reverse_current_max_a",
    )
    missing = [key for key in required if key not in device]
    if missing:
        raise ValueError(f"device validation limits missing keys: {missing}")

    ratio = transfer.get("on_off_current_ratio")
    ratio_limit = device["off_state_current_ratio_max"]
    ratio_passed = ratio is not None and ratio >= 1.0 / ratio_limit

    rds_value = rds.get("rds_on_ohm")
    rds_passed = (
        rds_value is not None
        and device["rds_on_min_ohm"] <= rds_value <= device["rds_on_max_ohm"]
    )

    drops = diode_forward.get("voltage_drops", {})
    drop_values = [
        item["forward_voltage_v"]
        for item in drops.values()
        if item.get("forward_voltage_v") is not None
    ]
    drop_passed = bool(drop_values) and all(
        device["diode_forward_drop_min_v"]
        <= value
        <= device["diode_forward_drop_max_v"]
        for value in drop_values
    )

    leakage = diode_reverse.get("max_abs_leakage_a")
    leakage_passed = (
        leakage is not None and abs(leakage) <= device["diode_reverse_current_max_a"]
    )

    checks = {
        "on_off_current_ratio": {
            "value": ratio,
            "limit": 1.0 / ratio_limit,
            "passed": bool(ratio_passed),
            "note": "on/off current ratio must exceed 1 / off_state_current_ratio_max",
        },
        "rds_on": {
            "value": rds_value,
            "limits": [device["rds_on_min_ohm"], device["rds_on_max_ohm"]],
            "passed": bool(rds_passed),
        },
        "diode_forward_drop": {
            "value": drop_values,
            "limits": [
                device["diode_forward_drop_min_v"],
                device["diode_forward_drop_max_v"],
            ],
            "passed": bool(drop_passed),
        },
        "diode_reverse_leakage": {
            "value": leakage,
            "limit": device["diode_reverse_current_max_a"],
            "passed": bool(leakage_passed),
        },
    }
    return {
        "passed": all(item["passed"] for item in checks.values()),
        "checks": checks,
        "note": "teaching limits from configs/nonideal_validation.yaml",
    }


def temperature_trend(entries: Iterable[dict[str, Any]], key: str) -> dict[str, Any]:
    """提取某指标随温度的变化趋势（仅排序输出，不做线性外推）。"""
    rows = [
        (float(item["temperature_c"]), item.get(key))
        for item in entries
        if item.get("temperature_c") is not None and item.get(key) is not None
    ]
    rows.sort(key=lambda pair: pair[0])
    if len(rows) < 2:
        return {"values": rows, "status": "insufficient_points"}
    values = np.asarray([value for _, value in rows], dtype=float)
    return {
        "values": [(temperature, float(value)) for temperature, value in rows],
        "change": float(values[-1] - values[0]),
        "relative_change_percent": (
            None if values[0] == 0 else float(100.0 * (values[-1] - values[0]) / abs(values[0]))
        ),
        "status": "ok",
    }

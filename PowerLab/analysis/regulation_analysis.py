"""负载调整率、输入调整率与线性拟合。

只使用真实仿真点；点数为 1 时返回 ``INSUFFICIENT_DATA``，不外推。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    r_squared: float
    points: int
    residual_max: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "slope": self.slope,
            "intercept": self.intercept,
            "r_squared": self.r_squared,
            "points": self.points,
            "residual_max": self.residual_max,
        }


def fit_linear(x_values: Iterable[float], y_values: Iterable[float]) -> LinearFit:
    """最小二乘直线拟合；点数不足或 x 无变化时抛错。"""
    x = np.asarray(list(x_values), dtype=float)
    y = np.asarray(list(y_values), dtype=float)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("x and y must be one-dimensional and equal length")
    if x.size < 2:
        raise ValueError("at least two points are required")
    if np.ptp(x) == 0:
        raise ValueError("x values must not be identical")
    slope, intercept = np.polyfit(x, y, 1)
    prediction = slope * x + intercept
    residual = y - prediction
    total = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - float(np.sum(residual**2)) / total if total > 0 else 1.0
    return LinearFit(
        slope=float(slope),
        intercept=float(intercept),
        r_squared=float(r_squared),
        points=int(x.size),
        residual_max=float(np.max(np.abs(residual))),
    )


def _point_value(point: Mapping[str, Any], key: str) -> float | None:
    value = point.get(key)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _is_steady(point: Mapping[str, Any]) -> bool:
    """``steady_state`` 缺失时视为可用；显式为假时剔除该点。"""
    if "steady_state" not in point:
        return True
    value = point["steady_state"]
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "")
    return bool(value)


def load_regulation(
    points: Iterable[Mapping[str, Any]],
    nominal_voltage_v: float,
) -> dict[str, Any]:
    """负载调整率：轻载到重载的输出电压变化。

    返回全范围跨度、CCM 范围跨度、CCM 斜率与轻载/重载端点差，
    并同时给出百分比与绝对值，避免只报一个友好数字。
    """
    nominal = float(nominal_voltage_v)
    if nominal <= 0:
        raise ValueError("nominal voltage must be positive")
    rows = [dict(item) for item in points]
    usable = [
        row
        for row in rows
        if _point_value(row, "load_resistance_ohm") is not None
        and _point_value(row, "output_voltage_v") is not None
        and _point_value(row, "output_current_a") is not None
        and _is_steady(row)
    ]
    excluded_not_settled = len(rows) - len(usable)
    if len(usable) < 2:
        return {
            "status": "INSUFFICIENT_DATA",
            "nominal_voltage_v": nominal,
            "points": len(usable),
            "excluded_not_settled": excluded_not_settled,
            "note": "at least two valid settled load points are required",
        }
    usable.sort(key=lambda row: float(row["output_current_a"]))
    currents = np.array([float(row["output_current_a"]) for row in usable], dtype=float)
    voltages = np.array([float(row["output_voltage_v"]) for row in usable], dtype=float)

    span = float(np.max(voltages) - np.min(voltages))
    span_percent = span / nominal * 100.0
    endpoint_delta = float(voltages[0] - voltages[-1])
    endpoint_percent = endpoint_delta / nominal * 100.0

    ccm_rows = [
        row
        for row in usable
        if str(row.get("conduction_mode", "CCM")).upper() == "CCM"
    ]
    result: dict[str, Any] = {
        "status": "AVAILABLE",
        "nominal_voltage_v": nominal,
        "points": len(usable),
        "excluded_not_settled": excluded_not_settled,
        "minimum_current_a": float(currents[0]),
        "maximum_current_a": float(currents[-1]),
        "minimum_voltage_v": float(np.min(voltages)),
        "maximum_voltage_v": float(np.max(voltages)),
        "span_v": span,
        "span_percent": float(span_percent),
        "endpoint_delta_v": endpoint_delta,
        "endpoint_percent": float(endpoint_percent),
        "ccm_points": len(ccm_rows),
        "data_source": "spice_simulation",
    }

    if len(ccm_rows) >= 2:
        ccm_currents = np.array(
            [float(row["output_current_a"]) for row in ccm_rows], dtype=float
        )
        ccm_voltages = np.array(
            [float(row["output_voltage_v"]) for row in ccm_rows], dtype=float
        )
        fit = fit_linear(ccm_currents, ccm_voltages)
        result.update(
            {
                "ccm_span_v": float(np.max(ccm_voltages) - np.min(ccm_voltages)),
                "ccm_slope_ohm": fit.slope,
                "ccm_slope_mv_per_a": float(fit.slope * 1e3),
                "ccm_intercept_v": fit.intercept,
                "ccm_r_squared": fit.r_squared,
            }
        )
    else:
        result.update(
            {
                "ccm_span_v": None,
                "ccm_slope_ohm": None,
                "ccm_slope_mv_per_a": None,
                "ccm_intercept_v": None,
                "ccm_r_squared": None,
            }
        )

    local_slopes = []
    for left, right in zip(usable[:-1], usable[1:]):
        delta_i = float(right["output_current_a"]) - float(left["output_current_a"])
        if delta_i == 0:
            continue
        local_slopes.append(
            (float(right["output_voltage_v"]) - float(left["output_voltage_v"])) / delta_i
        )
    result["local_slopes_ohm"] = [float(item) for item in local_slopes]
    return result


def line_regulation(
    points: Iterable[Mapping[str, Any]],
    nominal_voltage_v: float,
) -> dict[str, Any]:
    """输入调整率：输入电压变化时输出电压的变化。"""
    nominal = float(nominal_voltage_v)
    if nominal <= 0:
        raise ValueError("nominal voltage must be positive")
    rows = [dict(item) for item in points]
    usable = [
        row
        for row in rows
        if _point_value(row, "input_voltage_v") is not None
        and _point_value(row, "output_voltage_v") is not None
        and _is_steady(row)
    ]
    excluded_not_settled = len(rows) - len(usable)
    if len(usable) < 2:
        return {
            "status": "INSUFFICIENT_DATA",
            "nominal_voltage_v": nominal,
            "points": len(usable),
            "excluded_not_settled": excluded_not_settled,
            "note": "at least two valid settled input points are required",
        }
    usable.sort(key=lambda row: float(row["input_voltage_v"]))
    inputs = np.array([float(row["input_voltage_v"]) for row in usable], dtype=float)
    voltages = np.array([float(row["output_voltage_v"]) for row in usable], dtype=float)
    fit = fit_linear(inputs, voltages)
    span = float(np.max(voltages) - np.min(voltages))
    return {
        "status": "AVAILABLE",
        "nominal_voltage_v": nominal,
        "points": len(usable),
        "excluded_not_settled": excluded_not_settled,
        "minimum_input_voltage_v": float(inputs[0]),
        "maximum_input_voltage_v": float(inputs[-1]),
        "minimum_output_voltage_v": float(np.min(voltages)),
        "maximum_output_voltage_v": float(np.max(voltages)),
        "span_v": span,
        "span_percent": float(span / nominal * 100.0),
        "sensitivity_v_per_v": fit.slope,
        "sensitivity_mv_per_v": float(fit.slope * 1e3),
        "intercept_v": fit.intercept,
        "r_squared": fit.r_squared,
        "residual_max_v": fit.residual_max,
        "data_source": "spice_simulation",
    }

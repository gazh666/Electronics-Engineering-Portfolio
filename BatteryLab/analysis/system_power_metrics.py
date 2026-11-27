"""系统功率与能量指标。"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def mean_power(voltage_v: Sequence[float], current_a: Sequence[float]) -> float:
    v = np.asarray(voltage_v, dtype=float)
    i = np.asarray(current_a, dtype=float)
    if v.shape != i.shape:
        raise ValueError("电压电流长度不一致")
    if not (np.isfinite(v).all() and np.isfinite(i).all()):
        raise ValueError("功率计算包含非有限值")
    return float(np.mean(v * i))


def power_budget(
    *,
    battery_voltage_v: Sequence[float],
    battery_current_a: Sequence[float],
    converter_input_voltage_v: Sequence[float],
    converter_input_current_a: Sequence[float],
    output_voltage_v: Sequence[float],
    load_current_a: Sequence[float],
    path_resistance_ohm: float,
    steady_mask: Sequence[bool] | None = None,
) -> dict[str, float | None]:
    mask = np.asarray(steady_mask, dtype=bool) if steady_mask is not None else np.ones(len(battery_voltage_v), dtype=bool)
    if mask.sum() < 10:
        raise ValueError("稳态样本不足")

    def window(values: Sequence[float]) -> np.ndarray:
        return np.asarray(values, dtype=float)[mask]

    p_battery = mean_power(window(battery_voltage_v), window(battery_current_a))
    p_input = mean_power(window(converter_input_voltage_v), window(converter_input_current_a))
    p_output = mean_power(window(output_voltage_v), window(load_current_a))
    path_loss = float(np.mean(window(battery_current_a) ** 2) * path_resistance_ohm)
    return {
        "battery_power_w": p_battery,
        "protection_path_loss_w": path_loss,
        "converter_input_power_w": p_input,
        "converter_output_power_w": p_output,
        "converter_loss_w": p_input - p_output,
        "efficiency_percent": (p_output / p_input * 100.0) if p_input > 1e-12 else None,
        "boundary_residual_w": p_battery - path_loss - p_input,
        "boundary_residual_percent": (
            abs(p_battery - path_loss - p_input) / max(abs(p_battery), 1e-12) * 100.0
        ),
    }


__all__ = ["mean_power", "power_budget"]

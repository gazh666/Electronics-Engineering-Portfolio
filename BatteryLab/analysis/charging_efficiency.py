"""充电功率级效率与功率守恒分析。

效率口径必须明确：功率级效率只含 Vin→Vpack；系统效率再加入栅极驱动与辅助电源。
不允许把电池吸收能量全部视为可逆电化学储能，也不允许把超过 100% 的结果直接裁剪。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np


def _integrate(y: np.ndarray, x: np.ndarray) -> float:
    integrate = getattr(np, "trapezoid", None)
    if integrate is None:  # numpy < 2.0
        integrate = np.trapz
    return float(integrate(y, x))


def time_average(time_s: Any, values: Any) -> float:
    t = np.asarray(time_s, dtype=float)
    x = np.asarray(values, dtype=float)
    if t.ndim != 1 or x.ndim != 1:
        raise ValueError("Expected 1D arrays")
    if t.shape != x.shape or len(t) < 2:
        raise ValueError("Invalid waveform")
    if not (np.isfinite(t).all() and np.isfinite(x).all()):
        raise ValueError("Non-finite waveform")
    if not np.all(np.diff(t) > 0.0):
        raise ValueError("Invalid time axis")
    return _integrate(x, t) / float(t[-1] - t[0])


def window_mask(time_s: Any, start_s: float, stop_s: float) -> np.ndarray:
    t = np.asarray(time_s, dtype=float)
    if stop_s <= start_s:
        raise ValueError("Invalid window")
    return (t >= start_s) & (t <= stop_s)


def last_window_average(time_s: Any, values: Any, window_s: float) -> float:
    """最后 ``window_s`` 时间窗的时间加权平均（用于稳态指标）。"""
    t = np.asarray(time_s, dtype=float)
    x = np.asarray(values, dtype=float)
    if window_s <= 0.0:
        raise ValueError("Invalid window")
    start = float(t[-1] - window_s)
    mask = t >= start
    if mask.sum() < 2:
        raise ValueError("Window too short")
    return time_average(t[mask], x[mask])


def calculate_charger_efficiency(
    time_s: Any,
    input_voltage_v: Any,
    input_current_a: Any,
    pack_voltage_v: Any,
    charge_current_a: Any,
    driver_power_w: Any = None,
    auxiliary_power_w: Any = None,
) -> dict[str, float | None]:
    arrays = [
        np.asarray(x, dtype=float)
        for x in [input_voltage_v, input_current_a, pack_voltage_v, charge_current_a]
    ]
    t = np.asarray(time_s, dtype=float)
    if any(x.shape != t.shape for x in arrays):
        raise ValueError("Waveform shape mismatch")
    vin, iin, vbat, ibat = arrays

    p_in = time_average(t, vin * iin)
    p_bat = time_average(t, vbat * ibat)
    if p_in <= 0 or p_bat < 0:
        raise ValueError("Invalid charging power")

    result: dict[str, float | None] = {
        "input_power_w": p_in,
        "battery_power_w": p_bat,
        "power_stage_efficiency_percent": 100.0 * p_bat / p_in,
        "system_efficiency_percent": None,
    }

    if driver_power_w is not None and auxiliary_power_w is not None:
        driver = np.asarray(driver_power_w, dtype=float)
        auxiliary = np.asarray(auxiliary_power_w, dtype=float)
        if driver.shape != t.shape or auxiliary.shape != t.shape:
            raise ValueError("Power shape mismatch")
        p_total = p_in + time_average(t, driver) + time_average(t, auxiliary)
        if p_total <= 0:
            raise ValueError("Invalid total power")
        result["system_efficiency_percent"] = 100.0 * p_bat / p_total

    return result


def power_conservation_residual_fraction(
    input_power_w: float,
    battery_power_w: float,
    loss_power_w: float,
) -> float:
    """``(Pin - Pbat - Ploss) / Pin``；正数表示输入功率多出未解释部分。"""
    values = [input_power_w, battery_power_w, loss_power_w]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Non-finite power")
    if input_power_w <= 0:
        raise ValueError("Invalid input power")
    return (input_power_w - battery_power_w - loss_power_w) / input_power_w


def summarize_losses(losses_w: Sequence[tuple[str, float]], input_power_w: float) -> dict[str, Any]:
    if input_power_w <= 0:
        raise ValueError("Invalid input power")
    total = float(sum(value for _, value in losses_w))
    shares = {
        str(name): {
            "loss_w": float(value),
            "share_of_total_loss_percent": 100.0 * float(value) / total if total > 0 else None,
            "share_of_input_percent": 100.0 * float(value) / input_power_w,
        }
        for name, value in losses_w
    }
    return {"total_loss_w": total, "components": shares}

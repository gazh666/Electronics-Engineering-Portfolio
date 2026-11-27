"""极化建立与恢复的时间常数分析。"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd


class PolarizationError(ValueError):
    """极化分析输入非法。"""


def _sample_at(frame: pd.DataFrame, target_s: float) -> float | None:
    times = frame["time_s"].to_numpy(dtype=float)
    if target_s < times[0] - 1e-9 or target_s > times[-1] + 1e-9:
        return None
    index = int(np.argmin(np.abs(times - target_s)))
    return float(frame["polarization_1_v"].iloc[index] if "polarization_1_v" in frame.columns else frame.iloc[index]["polarization_2_v"])


def time_constant_checkpoints(
    frame: pd.DataFrame,
    *,
    pulse_start_s: float,
    pulse_end_s: float,
    tau_s: float,
    steady_voltage_v: float,
    column: str = "polarization_1_v",
    fractions: Sequence[float] = (0.5, 1.0, 2.0, 3.0, 5.0),
) -> list[dict[str, Any]]:
    """对照 0.5/1/2/3/5 tau 的理论极化比例与实际波形比例。

    建立阶段理论比例 ``1 - exp(-f)``，参考幅值取理论稳态 ``I*R``；
    恢复阶段理论剩余比例 ``exp(-f)``，参考幅值取断开前实际值。
    """
    if column not in frame.columns:
        raise PolarizationError(f"波形缺少列: {column}")
    if tau_s <= 0:
        raise PolarizationError("时间常数必须为正")
    if steady_voltage_v == 0:
        raise PolarizationError("稳态极化电压不能为零")
    times = frame["time_s"].to_numpy(dtype=float)
    values = frame[column].to_numpy(dtype=float)
    pulse_mask = (times >= pulse_start_s) & (times < pulse_end_s - 1e-12)
    if not pulse_mask.any():
        raise PolarizationError("脉冲区间没有采样点")
    recovery_start_value = float(values[np.searchsorted(times, pulse_end_s - 1e-12, side="left") - 1])

    rows: list[dict[str, Any]] = []
    for fraction in fractions:
        target = pulse_start_s + fraction * tau_s
        if target <= pulse_end_s + 1e-12:
            index = int(np.argmin(np.abs(times - target)))
            observed = float(values[index])
            theory = 1.0 - math.exp(-fraction)
            rows.append(
                {
                    "phase": "build",
                    "tau_multiple": float(fraction),
                    "target_time_s": float(target),
                    "actual_time_s": float(times[index]),
                    "theory_fraction": theory,
                    "observed_fraction": observed / steady_voltage_v,
                    "observed_voltage_v": observed,
                    "fraction_error": observed / steady_voltage_v - theory,
                }
            )
    for fraction in fractions:
        target = pulse_end_s + fraction * tau_s
        if target <= times[-1] + 1e-12:
            index = int(np.argmin(np.abs(times - target)))
            observed = float(values[index])
            theory = math.exp(-fraction)
            rows.append(
                {
                    "phase": "recovery",
                    "tau_multiple": float(fraction),
                    "target_time_s": float(target),
                    "actual_time_s": float(times[index]),
                    "theory_fraction": theory,
                    "observed_fraction": observed / recovery_start_value,
                    "observed_voltage_v": observed,
                    "fraction_error": observed / recovery_start_value - theory,
                }
            )
    return rows


def build_fraction_curve(tau_s: float, fractions: Sequence[float] = (0.0, 0.5, 1.0, 2.0, 3.0, 5.0)) -> list[dict[str, float]]:
    return [
        {"tau_multiple": float(fraction), "theory_fraction": 1.0 - math.exp(-float(fraction))}
        for fraction in fractions
    ]


def summarize_polarization(frame: pd.DataFrame, branches: int = 2) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "max_polarization_1_v": float(frame["polarization_1_v"].max()),
        "final_polarization_1_v": float(frame["polarization_1_v"].iloc[-1]),
        "final_stored_energy_j": float(frame["stored_energy_j"].iloc[-1]),
    }
    if branches >= 2:
        summary["max_polarization_2_v"] = float(frame["polarization_2_v"].max())
        summary["final_polarization_2_v"] = float(frame["polarization_2_v"].iloc[-1])
    return summary

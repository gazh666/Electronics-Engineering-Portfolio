"""电池功率与损耗分析。

端口功率 ``V*I``；欧姆损耗 ``I^2*R0``；极化电阻损耗 ``Vj^2/Rj``；
RC 支路储能 ``0.5*Cj*Vj^2``。
注意 ``I^2*R1`` 不等于瞬时极化电阻损耗，因为部分电流流经电容。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from battery_models.parameters import CellParameters, RCBranch


class LossAnalysisError(ValueError):
    """损耗分析输入非法。"""


def _trapezoid(values: np.ndarray, times: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(values, times))
    return float(np.trapz(values, times))  # pragma: no cover


def _select(frame: pd.DataFrame, start_s: float | None, end_s: float | None) -> pd.DataFrame:
    selected = frame
    if start_s is not None:
        selected = selected[selected["time_s"] >= float(start_s) - 1e-12]
    if end_s is not None:
        selected = selected[selected["time_s"] <= float(end_s) + 1e-12]
    if len(selected) < 2:
        raise LossAnalysisError("选定区间采样点不足")
    return selected


def instantaneous_losses(
    parameters: CellParameters,
    branches: Sequence[RCBranch],
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """基于波形列重建瞬时损耗（用于独立核查求解器输出）。"""
    result = pd.DataFrame({"time_s": frame["time_s"].to_numpy(dtype=float)})
    current = frame["current_a"].to_numpy(dtype=float)
    result["ohmic_loss_w"] = current**2 * parameters.r0_ohm
    total = np.zeros_like(current)
    for index, branch in enumerate(branches):
        column = f"polarization_{index + 1}_v"
        voltage = frame[column].to_numpy(dtype=float)
        loss = voltage**2 / branch.resistance_ohm
        result[f"branch{index + 1}_loss_w"] = loss
        total += loss
    result["polarization_resistor_loss_w"] = total
    return result


def integrate_losses(
    parameters: CellParameters,
    branches: Sequence[RCBranch],
    frame: pd.DataFrame,
    *,
    start_s: float | None = None,
    end_s: float | None = None,
) -> dict[str, Any]:
    """对选定区间积分端口能量、欧姆损耗与极化损耗。"""
    selected = _select(frame, start_s, end_s)
    times = selected["time_s"].to_numpy(dtype=float)
    current = selected["current_a"].to_numpy(dtype=float)
    terminal = selected["terminal_voltage_v"].to_numpy(dtype=float)

    ohmic_energy = _trapezoid(current**2 * parameters.r0_ohm, times)
    branch_energies: list[float] = []
    total_polarization = 0.0
    for index, branch in enumerate(branches):
        voltage = selected[f"polarization_{index + 1}_v"].to_numpy(dtype=float)
        energy = _trapezoid(voltage**2 / branch.resistance_ohm, times)
        branch_energies.append(energy)
        total_polarization += energy

    stored_start = float(selected["stored_energy_j"].iloc[0])
    stored_end = float(selected["stored_energy_j"].iloc[-1])
    duration = float(times[-1] - times[0])
    return {
        "time_start_s": float(times[0]),
        "time_end_s": float(times[-1]),
        "duration_s": duration,
        "terminal_energy_j": _trapezoid(terminal * current, times),
        "ohmic_energy_j": ohmic_energy,
        "polarization_energy_j": total_polarization,
        "branch_energies_j": branch_energies,
        "stored_energy_start_j": stored_start,
        "stored_energy_end_j": stored_end,
        "stored_energy_change_j": stored_end - stored_start,
        "mean_terminal_power_w": _trapezoid(terminal * current, times) / duration if duration > 0 else None,
        "mean_ohmic_power_w": ohmic_energy / duration if duration > 0 else None,
        "mean_polarization_power_w": total_polarization / duration if duration > 0 else None,
        "integration_method": "trapezoidal",
        "points": int(len(selected)),
    }

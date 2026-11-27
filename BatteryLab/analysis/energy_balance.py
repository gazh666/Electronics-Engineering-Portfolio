"""能量一致性验证。

Esource - Eterminal - Er0 - Erc - dErc_stored ≈ 0
其中 Esource = ∫OCV*I dt，Eterminal = ∫Vterminal*I dt，
Er0 = ∫I^2*R0 dt，Erc = ∫sum(Vj^2/Rj) dt。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd

from battery_models.parameters import CellParameters, RCBranch


class EnergyBalanceError(ValueError):
    """能量平衡输入非法。"""


def _trapezoid(values: np.ndarray, times: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(values, times))
    return float(np.trapz(values, times))  # pragma: no cover


def energy_balance(
    frame: pd.DataFrame,
    parameters: CellParameters,
    branches: Sequence[RCBranch],
    *,
    start_s: float | None = None,
    end_s: float | None = None,
    relative_threshold: float = 1.0e-3,
    absolute_threshold_j: float = 1.0e-6,
) -> dict[str, Any]:
    selected = frame
    if start_s is not None:
        selected = selected[selected["time_s"] >= float(start_s) - 1e-12]
    if end_s is not None:
        selected = selected[selected["time_s"] <= float(end_s) + 1e-12]
    if len(selected) < 2:
        raise EnergyBalanceError("选定区间采样点不足")

    times = selected["time_s"].to_numpy(dtype=float)
    current = selected["current_a"].to_numpy(dtype=float)
    ocv = selected["ocv_v"].to_numpy(dtype=float)
    terminal = selected["terminal_voltage_v"].to_numpy(dtype=float)

    source_energy = _trapezoid(ocv * current, times)
    terminal_energy = _trapezoid(terminal * current, times)
    ohmic_energy = _trapezoid(current**2 * parameters.r0_ohm, times)

    polarization_energy = 0.0
    branch_energies: list[float] = []
    for index, branch in enumerate(branches):
        voltage = selected[f"polarization_{index + 1}_v"].to_numpy(dtype=float)
        energy = _trapezoid(voltage**2 / branch.resistance_ohm, times)
        branch_energies.append(energy)
        polarization_energy += energy

    stored_voltages_start = [float(selected[f"polarization_{index + 1}_v"].iloc[0]) for index in range(len(branches))]
    stored_voltages_end = [float(selected[f"polarization_{index + 1}_v"].iloc[-1]) for index in range(len(branches))]
    stored_start = float(sum(0.5 * branch.capacitance_f * voltage**2 for branch, voltage in zip(branches, stored_voltages_start)))
    stored_end = float(sum(0.5 * branch.capacitance_f * voltage**2 for branch, voltage in zip(branches, stored_voltages_end)))
    stored_change = stored_end - stored_start

    residual = source_energy - terminal_energy - ohmic_energy - polarization_energy - stored_change
    scale = max(abs(source_energy), abs(terminal_energy), abs(ohmic_energy) + abs(polarization_energy), 1e-12)
    relative = abs(residual) / scale
    # 近零能量工况使用绝对判据，避免相对残差被极小分母放大。
    near_zero = max(abs(source_energy), abs(terminal_energy)) < 1.0

    return {
        "source_energy_j": source_energy,
        "terminal_energy_j": terminal_energy,
        "ohmic_energy_j": ohmic_energy,
        "polarization_energy_j": polarization_energy,
        "branch_energies_j": branch_energies,
        "stored_energy_start_j": stored_start,
        "stored_energy_end_j": stored_end,
        "stored_energy_change_j": stored_change,
        "residual_j": residual,
        "relative_residual": relative,
        "near_zero_energy": near_zero,
        "relative_threshold": float(relative_threshold),
        "absolute_threshold_j": float(absolute_threshold_j),
        "status": (
            "PASS_ABSOLUTE"
            if near_zero and abs(residual) <= absolute_threshold_j
            else (
                "PASS_RELATIVE"
                if not near_zero and relative <= relative_threshold and math.isfinite(relative)
                else "FAIL"
            )
        ),
        "integration_method": "trapezoidal",
        "time_start_s": float(times[0]),
        "time_end_s": float(times[-1]),
        "points": int(len(selected)),
    }

"""统一轻量 ECM 求解器：Rint（0 支路）、一阶 RC（1 支路）、二阶 RC（2 支路）。

时间离散采用零阶保持（ZOH）：区间 ``[t_k, t_k+1)`` 使用 ``I_k``，
RC 支路使用恒定电流下的解析解更新，SOC 使用精确电荷积分更新。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

from battery_models.parameters import CellParameters, RCBranch
from battery_models.states import (
    CellState,
    branch_dissipation_w,
    branch_stored_energy_j,
    update_branch_voltages,
    update_soc,
)

SECONDS_PER_HOUR = 3600.0

WAVEFORM_COLUMNS = (
    "time_s",
    "current_a",
    "soc",
    "ocv_v",
    "terminal_voltage_v",
    "ohmic_voltage_drop_v",
    "polarization_1_v",
    "polarization_2_v",
    "terminal_power_w",
    "ohmic_loss_w",
    "branch1_loss_w",
    "branch2_loss_w",
    "polarization_resistor_loss_w",
    "stored_energy_j",
    "capacity_throughput_ah",
)


class SolverError(ValueError):
    """求解输入非法。"""


@dataclass
class EcmResult:
    """一次 ECM 求解结果。"""

    frame: pd.DataFrame
    events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def termination(self) -> str:
        return str(self.metadata.get("termination", "completed"))

    def summary(self) -> dict[str, Any]:
        frame = self.frame
        return {
            "model": self.metadata.get("model"),
            "points": int(len(frame)),
            "time_start_s": float(frame["time_s"].iloc[0]),
            "time_end_s": float(frame["time_s"].iloc[-1]),
            "soc_start": float(frame["soc"].iloc[0]),
            "soc_end": float(frame["soc"].iloc[-1]),
            "terminal_voltage_start_v": float(frame["terminal_voltage_v"].iloc[0]),
            "terminal_voltage_end_v": float(frame["terminal_voltage_v"].iloc[-1]),
            "terminal_voltage_min_v": float(frame["terminal_voltage_v"].min()),
            "terminal_voltage_max_v": float(frame["terminal_voltage_v"].max()),
            "capacity_throughput_ah": float(frame["capacity_throughput_ah"].iloc[-1]),
            "termination": self.metadata.get("termination"),
            "termination_time_s": self.metadata.get("termination_time_s"),
            "termination_reason": self.metadata.get("termination_reason"),
        }


def _as_series(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise SolverError(f"{name} 必须是一维数组")
    if array.size < 2:
        raise SolverError(f"{name} 至少需要两个采样点")
    if not np.isfinite(array).all():
        raise SolverError(f"{name} 含有非有限数值")
    return array


def _validate_inputs(
    parameters: CellParameters,
    rc_branches: Sequence[RCBranch],
    initial_state: CellState,
    time_s: Any,
    current_a: Any,
) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(parameters, CellParameters):
        raise SolverError("parameters 必须是 CellParameters")
    if len(initial_state.polarization_voltages_v) != len(rc_branches):
        raise SolverError("初始极化电压数量与 RC 支路数量不一致")
    time_array = _as_series(time_s, "time_s")
    current_array = _as_series(current_a, "current_a")
    if time_array.size != current_array.size:
        raise SolverError("时间轴与电流序列长度不一致")
    if not np.all(np.diff(time_array) > 0.0):
        raise SolverError("时间必须严格递增")
    return time_array, current_array


def terminal_voltage(
    parameters: CellParameters,
    rc_branches: Sequence[RCBranch],
    polarization_voltages_v: Sequence[float],
    ocv_v: float,
    current_a: float,
) -> float:
    """Vterminal = OCV - I*R0 - sum(Vj)。"""
    return float(ocv_v) - float(current_a) * parameters.r0_ohm - float(sum(polarization_voltages_v))


def _loss_terms(
    parameters: CellParameters,
    rc_branches: Sequence[RCBranch],
    polarization_voltages_v: Sequence[float],
    current_a: float,
) -> tuple[float, tuple[float, ...], float]:
    ohmic = current_a**2 * parameters.r0_ohm
    branch_losses = branch_dissipation_w(rc_branches, polarization_voltages_v)
    return ohmic, branch_losses, float(sum(branch_losses))


def _row(
    time_value: float,
    current_value: float,
    state: CellState,
    ocv_value: float,
    parameters: CellParameters,
    rc_branches: Sequence[RCBranch],
    capacity_throughput_ah: float,
) -> dict[str, Any]:
    voltages = state.polarization_voltages_v
    terminal = terminal_voltage(parameters, rc_branches, voltages, ocv_value, current_value)
    ohmic, branch_losses, total_polarization_loss = _loss_terms(parameters, rc_branches, voltages, current_value)
    stored = branch_stored_energy_j(rc_branches, voltages)
    return {
        "time_s": float(time_value),
        "current_a": float(current_value),
        "soc": float(state.soc),
        "ocv_v": float(ocv_value),
        "terminal_voltage_v": terminal,
        "ohmic_voltage_drop_v": float(current_value) * parameters.r0_ohm,
        "polarization_1_v": float(voltages[0]) if len(voltages) > 0 else 0.0,
        "polarization_2_v": float(voltages[1]) if len(voltages) > 1 else 0.0,
        "terminal_power_w": terminal * float(current_value),
        "ohmic_loss_w": float(ohmic),
        "branch1_loss_w": float(branch_losses[0]) if len(branch_losses) > 0 else 0.0,
        "branch2_loss_w": float(branch_losses[1]) if len(branch_losses) > 1 else 0.0,
        "polarization_resistor_loss_w": total_polarization_loss,
        "stored_energy_j": float(sum(stored)),
        "capacity_throughput_ah": float(capacity_throughput_ah),
    }


def _limit_violation(
    soc: float,
    terminal_v: float,
    lower_voltage_v: float,
    upper_voltage_v: float,
) -> str | None:
    if soc < 0.0:
        return "soc_lower_limit"
    if soc > 1.0:
        return "soc_upper_limit"
    if terminal_v < lower_voltage_v:
        return "terminal_voltage_lower_limit"
    if terminal_v > upper_voltage_v:
        return "terminal_voltage_upper_limit"
    return None


def simulate_ecm(
    parameters: CellParameters,
    rc_branches: Sequence[RCBranch],
    initial_state: CellState,
    time_s: Any,
    current_a: Any,
    ocv_model: Any,
    *,
    model_name: str = "custom_ecm",
    output_step_s: float | None = None,
    lower_voltage_v: float | None = None,
    upper_voltage_v: float | None = None,
    stop_on_limits: bool = True,
    data_source: str = "custom_ecm_simulation",
    extra_metadata: dict[str, Any] | None = None,
) -> EcmResult:
    """执行 ECM 数值求解。

    ``time_s`` 与 ``current_a`` 为同一时间轴上的采样，电流在区间内保持左端值。
    """
    time_array, current_array = _validate_inputs(parameters, rc_branches, initial_state, time_s, current_a)
    lower = parameters.lower_voltage_v if lower_voltage_v is None else float(lower_voltage_v)
    upper = parameters.upper_voltage_v if upper_voltage_v is None else float(upper_voltage_v)
    if lower >= upper:
        raise SolverError("下限电压必须小于上限电压")

    events: list[dict[str, Any]] = []
    for index in range(time_array.size - 1):
        delta = float(current_array[index + 1] - current_array[index])
        if abs(delta) > 1e-12:
            events.append(
                {
                    "event_type": "current_step",
                    "time_s": float(time_array[index + 1]),
                    "current_before_a": float(current_array[index]),
                    "current_after_a": float(current_array[index + 1]),
                    "delta_current_a": delta,
                }
            )

    state = initial_state
    throughput = 0.0
    rows: list[dict[str, Any]] = []
    termination = "completed"
    termination_time = float(time_array[-1])
    termination_reason = ""

    for index in range(time_array.size - 1):
        current_value = float(current_array[index])
        ocv_value = float(ocv_model.voltage(state.soc))
        rows.append(
            _row(
                float(time_array[index]),
                current_value,
                state,
                ocv_value,
                parameters,
                rc_branches,
                throughput,
            )
        )

        dt = float(time_array[index + 1] - time_array[index])
        next_soc = update_soc(
            state.soc,
            current_value,
            dt,
            parameters.capacity_ah,
            parameters.charge_efficiency,
            parameters.discharge_efficiency,
        )
        next_voltages = update_branch_voltages(
            state.polarization_voltages_v, rc_branches, current_value, dt
        )
        increment_ah = current_value * dt / SECONDS_PER_HOUR
        throughput_next = throughput + increment_ah
        next_current = float(current_array[index + 1])
        next_ocv = float(ocv_model.voltage(min(max(next_soc, 0.0), 1.0)))
        next_terminal = terminal_voltage(parameters, rc_branches, next_voltages, next_ocv, next_current)

        violation = _limit_violation(next_soc, next_terminal, lower, upper) if stop_on_limits else None
        if violation is not None:
            if violation.startswith("soc"):
                previous_measure = state.soc
                next_measure = next_soc
                target = 0.0 if violation == "soc_lower_limit" else 1.0
            else:
                previous_measure = rows[-1]["terminal_voltage_v"]
                next_measure = next_terminal
                target = lower if violation == "terminal_voltage_lower_limit" else upper
            denominator = next_measure - previous_measure
            fraction = 1.0 if abs(denominator) < 1e-15 else (target - previous_measure) / denominator
            fraction = float(min(max(fraction, 0.0), 1.0))
            crossing_time = float(time_array[index]) + fraction * dt
            crossing_state = CellState(
                soc=state.soc + fraction * (next_soc - state.soc),
                polarization_voltages_v=tuple(
                    current + fraction * (following - current)
                    for current, following in zip(state.polarization_voltages_v, next_voltages)
                ),
            )
            crossing_row = _row(
                crossing_time,
                current_value,
                crossing_state,
                float(ocv_model.voltage(min(max(crossing_state.soc, 0.0), 1.0))),
                parameters,
                rc_branches,
                throughput + fraction * increment_ah,
            )
            crossing_row["termination_flag"] = violation
            rows.append(crossing_row)
            termination = "terminated"
            termination_time = crossing_time
            termination_reason = violation
            events.append(
                {
                    "event_type": "termination",
                    "time_s": crossing_time,
                    "reason": violation,
                    "soc": crossing_state.soc,
                    "terminal_voltage_v": crossing_row["terminal_voltage_v"],
                }
            )
            break

        if stop_on_limits:
            state = CellState(soc=next_soc, polarization_voltages_v=next_voltages)
        else:
            state = CellState(
                soc=min(max(next_soc, 0.0), 1.0), polarization_voltages_v=next_voltages
            )
        throughput = throughput_next

    if termination == "completed":
        current_value = float(current_array[-1])
        ocv_value = float(ocv_model.voltage(state.soc))
        rows.append(
            _row(
                float(time_array[-1]),
                current_value,
                state,
                ocv_value,
                parameters,
                rc_branches,
                throughput,
            )
        )

    frame = pd.DataFrame(rows)
    if "termination_flag" in frame.columns:
        frame["termination_flag"] = frame["termination_flag"].fillna("")
    else:
        frame["termination_flag"] = ""
    frame = frame[list(WAVEFORM_COLUMNS) + ["termination_flag"]]

    steps = np.diff(time_array)
    metadata = {
        "model": model_name,
        "model_order": len(rc_branches),
        "parameter_source": parameters.parameter_source,
        "data_source": data_source,
        "solver_method": "exact_zero_order_hold_exponential_update",
        "parameters": parameters.__dict__.copy(),
        "rc_branches": [
            {
                "resistance_ohm": branch.resistance_ohm,
                "capacitance_f": branch.capacitance_f,
                "time_constant_s": branch.time_constant_s,
            }
            for branch in rc_branches
        ],
        "initial_state": {
            "soc": initial_state.soc,
            "polarization_voltages_v": list(initial_state.polarization_voltages_v),
        },
        "ocv": ocv_model.metadata() if hasattr(ocv_model, "metadata") else {"ocv_model": "unknown"},
        "time_step": {
            "min_s": float(steps.min()),
            "max_s": float(steps.max()),
            "mean_s": float(steps.mean()),
            "requested_output_step_s": output_step_s,
        },
        "points": int(len(frame)),
        "requested_duration_s": float(time_array[-1] - time_array[0]),
        "termination": termination,
        "termination_time_s": termination_time,
        "termination_reason": termination_reason,
        "limits": {"lower_voltage_v": lower, "upper_voltage_v": upper, "soc_min": 0.0, "soc_max": 1.0},
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return EcmResult(frame=frame, events=events, metadata=metadata)

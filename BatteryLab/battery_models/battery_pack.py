"""3S1P 串联电池组模型。

串联条件下各电芯电流相同：``Icell1 = Icell2 = Icell3 = Ipack``；
电池组电压为各单体的差分电压之和：``Vpack = sum(Vcell_k)``。
本阶段不启用均衡支路与并联电流路径，也不代表已完成真实 BMS 保护电路。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Sequence

import numpy as np
import pandas as pd

from battery_models.ecm_solver import terminal_voltage
from battery_models.parameters import CellParameters, ECMModelDefinition, RCBranch
from battery_models.states import (
    CellState,
    branch_dissipation_w,
    branch_stored_energy_j,
    update_branch_voltages,
    update_soc,
)

SECONDS_PER_HOUR = 3600.0

PACK_COLUMNS = (
    "time_s",
    "current_a",
    "pack_voltage_v",
    "pack_power_w",
    "pack_ohmic_loss_w",
    "pack_polarization_loss_w",
    "sum_cell_voltage_v",
    "voltage_sum_error_v",
    "max_cell_voltage_v",
    "min_cell_voltage_v",
    "delta_cell_voltage_v",
    "max_soc",
    "min_soc",
    "delta_soc",
    "mean_soc",
    "first_limited_cell",
)

CELL_COLUMNS = (
    "time_s",
    "current_a",
    "cell_id",
    "soc",
    "ocv_v",
    "terminal_voltage_v",
    "ohmic_loss_w",
    "polarization_resistor_loss_w",
    "stored_energy_j",
)


class PackError(ValueError):
    """电池组输入非法。"""


class PackCellModel:
    """一节可独立演化的 ECM 电芯。"""

    def __init__(
        self,
        cell_id: str,
        parameters: CellParameters,
        branches: Sequence[RCBranch],
        ocv_model: Any,
        initial_state: CellState,
        initial_soc: float | None = None,
    ) -> None:
        if not isinstance(parameters, CellParameters):
            raise PackError("parameters 必须是 CellParameters")
        if len(initial_state.polarization_voltages_v) != len(branches):
            raise PackError("初始极化电压数量与 RC 支路数量不一致")
        self.cell_id = str(cell_id)
        self.parameters = parameters
        self.branches = tuple(branches)
        self.ocv_model = ocv_model
        self.initial_state = initial_state
        self.initial_soc = float(initial_state.soc if initial_soc is None else initial_soc)
        self.state = initial_state

    @property
    def order(self) -> int:
        return len(self.branches)

    def ocv_v(self) -> float:
        return float(self.ocv_model.voltage(self.state.soc))

    def terminal_voltage_v(self, current_a: float) -> float:
        return terminal_voltage(self.parameters, self.branches, self.state.polarization_voltages_v, self.ocv_v(), current_a)

    def ohmic_loss_w(self, current_a: float) -> float:
        return float(current_a) ** 2 * self.parameters.r0_ohm

    def polarization_loss_w(self) -> float:
        return float(sum(branch_dissipation_w(self.branches, self.state.polarization_voltages_v)))

    def stored_energy_j(self) -> float:
        return float(sum(branch_stored_energy_j(self.branches, self.state.polarization_voltages_v)))

    def step(self, current_a: float, dt_s: float) -> None:
        next_soc = update_soc(
            self.state.soc,
            current_a,
            dt_s,
            self.parameters.capacity_ah,
            self.parameters.charge_efficiency,
            self.parameters.discharge_efficiency,
        )
        next_voltages = update_branch_voltages(self.state.polarization_voltages_v, self.branches, current_a, dt_s)
        self.state = CellState(soc=next_soc, polarization_voltages_v=next_voltages)

    def snapshot(self, current_a: float) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "soc": self.state.soc,
            "ocv_v": self.ocv_v(),
            "terminal_voltage_v": self.terminal_voltage_v(current_a),
            "ohmic_loss_w": self.ohmic_loss_w(current_a),
            "polarization_resistor_loss_w": self.polarization_loss_w(),
            "stored_energy_j": self.stored_energy_j(),
            "r0_ohm": self.parameters.r0_ohm,
            "capacity_ah": self.parameters.capacity_ah,
            "initial_soc": self.initial_soc,
        }


class SeriesBatteryPack:
    """3S1P 串联电池组（也支持任意节数，用于教学对照）。"""

    def __init__(self, cells: Sequence[PackCellModel], name: str = "3S1P") -> None:
        if not cells:
            raise PackError("电池组至少需要一节电芯")
        identifiers = [cell.cell_id for cell in cells]
        if len(set(identifiers)) != len(identifiers):
            raise PackError("电芯编号必须唯一")
        self.cells = list(cells)
        self.name = name
        self.topology = f"{len(self.cells)}S1P"

    def step(self, current_a: float, dt_s: float) -> None:
        for cell in self.cells:
            cell.step(current_a, dt_s)

    def cell_voltages(self, current_a: float) -> tuple[float, ...]:
        return tuple(cell.terminal_voltage_v(current_a) for cell in self.cells)

    def pack_voltage(self, current_a: float) -> float:
        return float(sum(self.cell_voltages(current_a)))

    def pack_ohmic_loss_w(self, current_a: float) -> float:
        return float(sum(cell.ohmic_loss_w(current_a) for cell in self.cells))

    def pack_polarization_loss_w(self) -> float:
        return float(sum(cell.polarization_loss_w() for cell in self.cells))

    def total_r0_ohm(self) -> float:
        return float(sum(cell.parameters.r0_ohm for cell in self.cells))

    @property
    def socs(self) -> tuple[float, ...]:
        return tuple(cell.state.soc for cell in self.cells)

    def max_voltage_delta(self, current_a: float) -> float:
        voltages = self.cell_voltages(current_a)
        return float(max(voltages) - min(voltages))


def build_uniform_pack(
    definition: ECMModelDefinition,
    ocv_model: Any,
    *,
    count: int = 3,
    initial_soc: float = 0.6,
) -> SeriesBatteryPack:
    cells = [
        PackCellModel(
            f"cell{index + 1}",
            replace(definition.parameters, label=f"cell{index + 1}"),
            definition.branches,
            ocv_model,
            CellState.initial(initial_soc, definition.order),
            initial_soc=initial_soc,
        )
        for index in range(count)
    ]
    return SeriesBatteryPack(cells, name=f"{count}S1P")


def build_inconsistent_pack(
    definition: ECMModelDefinition,
    ocv_model: Any,
    *,
    socs: Sequence[float],
    capacities_ah: Sequence[float] | None = None,
    r0_ohm: Sequence[float] | None = None,
) -> SeriesBatteryPack:
    count = len(socs)
    capacities = list(capacities_ah) if capacities_ah is not None else [definition.parameters.capacity_ah] * count
    resistances = list(r0_ohm) if r0_ohm is not None else [definition.parameters.r0_ohm] * count
    if len(capacities) != count or len(resistances) != count:
        raise PackError("容量/内阻不一致参数长度必须与 SOC 列表一致")
    cells = [
        PackCellModel(
            f"cell{index + 1}",
            replace(
                definition.parameters,
                capacity_ah=capacities[index],
                r0_ohm=resistances[index],
                label=f"cell{index + 1}",
            ),
            definition.branches,
            ocv_model,
            CellState.initial(socs[index], definition.order),
            initial_soc=socs[index],
        )
        for index in range(count)
    ]
    return SeriesBatteryPack(cells, name=f"{count}S1P")


def _pack_row(
    time_value: float,
    current_value: float,
    pack: SeriesBatteryPack,
    first_limited_cell: str = "",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    voltages = pack.cell_voltages(current_value)
    socs = pack.socs
    pack_voltage = float(sum(voltages))
    sum_voltage = float(sum(voltages))
    pack_row = {
        "time_s": float(time_value),
        "current_a": float(current_value),
        "pack_voltage_v": pack_voltage,
        "pack_power_w": pack_voltage * float(current_value),
        "pack_ohmic_loss_w": pack.pack_ohmic_loss_w(current_value),
        "pack_polarization_loss_w": pack.pack_polarization_loss_w(),
        "sum_cell_voltage_v": sum_voltage,
        "voltage_sum_error_v": pack_voltage - sum_voltage,
        "max_cell_voltage_v": float(max(voltages)),
        "min_cell_voltage_v": float(min(voltages)),
        "delta_cell_voltage_v": float(max(voltages) - min(voltages)),
        "max_soc": float(max(socs)),
        "min_soc": float(min(socs)),
        "delta_soc": float(max(socs) - min(socs)),
        "mean_soc": float(sum(socs) / len(socs)),
        "first_limited_cell": first_limited_cell,
    }
    cell_rows = []
    for cell in pack.cells:
        snapshot = cell.snapshot(current_value)
        cell_rows.append(
            {
                "time_s": float(time_value),
                "current_a": float(current_value),
                "cell_id": cell.cell_id,
                "soc": snapshot["soc"],
                "ocv_v": snapshot["ocv_v"],
                "terminal_voltage_v": snapshot["terminal_voltage_v"],
                "ohmic_loss_w": snapshot["ohmic_loss_w"],
                "polarization_resistor_loss_w": snapshot["polarization_resistor_loss_w"],
                "stored_energy_j": snapshot["stored_energy_j"],
            }
        )
    return pack_row, cell_rows


def _limit_reason(cell: PackCellModel, soc: float, voltage: float) -> str | None:
    if soc < 0.0:
        return "soc_lower_limit"
    if soc > 1.0:
        return "soc_upper_limit"
    if voltage < cell.parameters.lower_voltage_v:
        return "cell_voltage_lower_limit"
    if voltage > cell.parameters.upper_voltage_v:
        return "cell_voltage_upper_limit"
    return None


def simulate_series_pack(
    pack: SeriesBatteryPack,
    time_s: Any,
    current_a: Any,
    *,
    stop_on_limits: bool = True,
    data_source: str = "custom_ecm_simulation",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """对串联电池组执行零阶保持数值仿真，返回包波形、单体波形与元数据。"""
    time_array = np.asarray(time_s, dtype=float)
    current_array = np.asarray(current_a, dtype=float)
    if time_array.ndim != 1 or current_array.ndim != 1:
        raise PackError("时间与电流必须是一维数组")
    if time_array.size != current_array.size or time_array.size < 2:
        raise PackError("时间与电流长度必须一致且至少两个点")
    if not np.isfinite(time_array).all() or not np.isfinite(current_array).all():
        raise PackError("时间与电流必须为有限数值")
    if not np.all(np.diff(time_array) > 0.0):
        raise PackError("时间必须严格递增")

    events: list[dict[str, Any]] = []
    for index in range(time_array.size - 1):
        if abs(current_array[index + 1] - current_array[index]) > 1e-12:
            events.append(
                {
                    "event_type": "current_step",
                    "time_s": float(time_array[index + 1]),
                    "current_before_a": float(current_array[index]),
                    "current_after_a": float(current_array[index + 1]),
                }
            )

    pack_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    termination = "completed"
    termination_time = float(time_array[-1])
    termination_reason = ""
    termination_cell = ""

    for index in range(time_array.size - 1):
        current_value = float(current_array[index])
        pack_row, rows = _pack_row(float(time_array[index]), current_value, pack)
        pack_rows.append(pack_row)
        cell_rows.extend(rows)

        dt = float(time_array[index + 1] - time_array[index])
        next_current = float(current_array[index + 1])
        candidates: list[tuple[float, int, str, str]] = []
        next_pairs: list[tuple[float, tuple[float, ...]]] = []
        for cell_index, cell in enumerate(pack.cells):
            next_soc = update_soc(
                cell.state.soc,
                current_value,
                dt,
                cell.parameters.capacity_ah,
                cell.parameters.charge_efficiency,
                cell.parameters.discharge_efficiency,
            )
            next_voltages = update_branch_voltages(
                cell.state.polarization_voltages_v, cell.branches, current_value, dt
            )
            next_pairs.append((next_soc, next_voltages))
            next_ocv = float(cell.ocv_model.voltage(min(max(next_soc, 0.0), 1.0)))
            next_terminal = terminal_voltage(cell.parameters, cell.branches, next_voltages, next_ocv, next_current)
            reason = _limit_reason(cell, next_soc, next_terminal) if stop_on_limits else None
            if reason is None:
                continue
            if reason.startswith("soc"):
                previous_measure = cell.state.soc
                next_measure = next_soc
                target = 0.0 if reason == "soc_lower_limit" else 1.0
            else:
                previous_measure = cell.terminal_voltage_v(current_value)
                next_measure = next_terminal
                target = (
                    cell.parameters.lower_voltage_v
                    if reason == "cell_voltage_lower_limit"
                    else cell.parameters.upper_voltage_v
                )
            denominator = next_measure - previous_measure
            fraction = 1.0 if abs(denominator) < 1e-15 else (target - previous_measure) / denominator
            candidates.append((float(min(max(fraction, 0.0), 1.0)), cell_index, reason, cell.cell_id))

        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]))
            fraction, cell_index, reason, cell_id = candidates[0]
            crossing_time = float(time_array[index]) + fraction * dt
            for position, cell in enumerate(pack.cells):
                next_soc, next_voltages = next_pairs[position]
                cell.state = CellState(
                    soc=cell.state.soc + fraction * (next_soc - cell.state.soc),
                    polarization_voltages_v=tuple(
                        previous + fraction * (following - previous)
                        for previous, following in zip(cell.state.polarization_voltages_v, next_voltages)
                    ),
                )
            pack_row, rows = _pack_row(crossing_time, current_value, pack, first_limited_cell=cell_id)
            pack_row["first_limited_cell"] = cell_id
            pack_rows.append(pack_row)
            cell_rows.extend(rows)
            termination = "terminated"
            termination_time = crossing_time
            termination_reason = reason
            termination_cell = cell_id
            events.append(
                {
                    "event_type": "termination",
                    "time_s": crossing_time,
                    "reason": reason,
                    "cell_id": cell_id,
                }
            )
            break

        for cell, (next_soc, next_voltages) in zip(pack.cells, next_pairs):
            if stop_on_limits:
                cell.state = CellState(soc=next_soc, polarization_voltages_v=next_voltages)
            else:
                cell.state = CellState(
                    soc=min(max(next_soc, 0.0), 1.0), polarization_voltages_v=next_voltages
                )

    if termination == "completed":
        current_value = float(current_array[-1])
        pack_row, rows = _pack_row(float(time_array[-1]), current_value, pack)
        pack_rows.append(pack_row)
        cell_rows.extend(rows)

    pack_frame = pd.DataFrame(pack_rows)[list(PACK_COLUMNS)]
    cell_frame = pd.DataFrame(cell_rows)[list(CELL_COLUMNS)]
    metadata = {
        "pack_name": pack.name,
        "topology": pack.topology,
        "series_cells": len(pack.cells),
        "parallel_cells": 1,
        "data_source": data_source,
        "solver_method": "exact_zero_order_hold_exponential_update",
        "total_r0_ohm": pack.total_r0_ohm(),
        "cells": [
            {
                "cell_id": cell.cell_id,
                "capacity_ah": cell.parameters.capacity_ah,
                "r0_ohm": cell.parameters.r0_ohm,
                "initial_soc": cell.initial_soc,
                "order": cell.order,
                "time_constants_s": [branch.time_constant_s for branch in cell.branches],
                "parameter_source": cell.parameters.parameter_source,
            }
            for cell in pack.cells
        ],
        "termination": termination,
        "termination_time_s": termination_time,
        "termination_reason": termination_reason,
        "termination_cell": termination_cell,
        "points": int(len(pack_frame)),
        "final_max_cell_voltage_v": float(pack_frame["max_cell_voltage_v"].iloc[-1]),
        "final_min_cell_voltage_v": float(pack_frame["min_cell_voltage_v"].iloc[-1]),
        "final_delta_cell_voltage_v": float(pack_frame["delta_cell_voltage_v"].iloc[-1]),
        "max_delta_cell_voltage_v": float(pack_frame["delta_cell_voltage_v"].max()),
        "max_delta_soc": float(pack_frame["delta_soc"].max()),
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "pack_frame": pack_frame,
        "cell_frame": cell_frame,
        "events": events,
        "metadata": metadata,
    }

"""3S 电池组一致性指标。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


class PackConsistencyError(ValueError):
    """电池组波形非法。"""


def consistency_metrics(pack_frame: pd.DataFrame, cell_frame: pd.DataFrame) -> dict[str, Any]:
    required_pack = ("time_s", "pack_voltage_v", "delta_cell_voltage_v", "sum_cell_voltage_v")
    required_cell = ("time_s", "cell_id", "terminal_voltage_v", "soc", "ohmic_loss_w", "polarization_resistor_loss_w")
    for column in required_pack:
        if column not in pack_frame.columns:
            raise PackConsistencyError(f"电池组波形缺少列: {column}")
    for column in required_cell:
        if column not in cell_frame.columns:
            raise PackConsistencyError(f"单体波形缺少列: {column}")

    voltage_sum_error = float(np.max(np.abs(pack_frame["pack_voltage_v"] - pack_frame["sum_cell_voltage_v"].astype(float))))

    pivot = cell_frame.pivot_table(index="time_s", columns="cell_id", values="terminal_voltage_v")
    max_cell = pivot.max(axis=1)
    min_cell = pivot.min(axis=1)
    delta = max_cell - min_cell
    recomputed_delta_error = float(np.max(np.abs(delta.to_numpy() - pack_frame["delta_cell_voltage_v"].to_numpy(dtype=float))))

    soc_pivot = cell_frame.pivot_table(index="time_s", columns="cell_id", values="soc")
    soc_spread = soc_pivot.max(axis=1) - soc_pivot.min(axis=1)

    loss_sum = cell_frame.groupby("time_s")[["ohmic_loss_w", "polarization_resistor_loss_w"]].sum()
    loss_sum["total"] = loss_sum["ohmic_loss_w"] + loss_sum["polarization_resistor_loss_w"]
    pack_loss = pack_frame.set_index("time_s")["pack_ohmic_loss_w"] + pack_frame.set_index("time_s")["pack_polarization_loss_w"]
    loss_error = float(np.max(np.abs(loss_sum["total"] - pack_loss)))

    final_time = float(pack_frame["time_s"].iloc[-1])
    final_cell = cell_frame[cell_frame["time_s"] >= final_time - 1e-9]
    return {
        "points": int(len(pack_frame)),
        "cells": int(cell_frame["cell_id"].nunique()),
        "max_voltage_sum_error_v": voltage_sum_error,
        "max_delta_cell_voltage_v": float(pack_frame["delta_cell_voltage_v"].max()),
        "final_delta_cell_voltage_v": float(pack_frame["delta_cell_voltage_v"].iloc[-1]),
        "max_delta_soc": float(soc_spread.max()),
        "final_delta_soc": float(soc_spread.iloc[-1]),
        "max_delta_recompute_error_v": recomputed_delta_error,
        "max_loss_sum_error_w": loss_error,
        "final_cell_voltages_v": {str(row["cell_id"]): float(row["terminal_voltage_v"]) for _, row in final_cell.iterrows()},
        "final_cell_socs": {str(row["cell_id"]): float(row["soc"]) for _, row in final_cell.iterrows()},
        "pack_voltage_start_v": float(pack_frame["pack_voltage_v"].iloc[0]),
        "pack_voltage_end_v": float(pack_frame["pack_voltage_v"].iloc[-1]),
        "pack_voltage_min_v": float(pack_frame["pack_voltage_v"].min()),
        "pack_voltage_max_v": float(pack_frame["pack_voltage_v"].max()),
    }

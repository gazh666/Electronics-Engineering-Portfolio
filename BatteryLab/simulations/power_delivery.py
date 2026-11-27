"""理想恒阻 / 恒功率负载下的电池组响应。

负载电流随电池状态变化，不能假设整段电流不变后直接使用 ZOH；
本模块按小时间步迭代，并在演示脚本中对步长细化做一致性检查。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from battery_models.battery_pack import SeriesBatteryPack
from battery_models.states import update_soc, update_branch_voltages


class PowerDeliveryError(ValueError):
    """负载条件不可行或参数非法。"""


def effective_source_voltage_v(pack: SeriesBatteryPack) -> float:
    """Ueffective = sum(OCV_i - Vpolarization_i)。"""
    total = 0.0
    for cell in pack.cells:
        total += float(cell.ocv_model.voltage(cell.state.soc)) - float(
            sum(cell.state.polarization_voltages_v)
        )
    return total


def total_series_resistance_ohm(pack: SeriesBatteryPack) -> float:
    return float(sum(cell.parameters.r0_ohm for cell in pack.cells))


def _termination_reason(pack: SeriesBatteryPack, current_a: float) -> tuple[str, str]:
    for cell in pack.cells:
        if cell.state.soc < 0.0:
            return "soc_lower_limit", cell.cell_id
        if cell.state.soc > 1.0:
            return "soc_upper_limit", cell.cell_id
        voltage = cell.terminal_voltage_v(current_a)
        if voltage < cell.parameters.lower_voltage_v:
            return "cell_voltage_lower_limit", cell.cell_id
        if voltage > cell.parameters.upper_voltage_v:
            return "cell_voltage_upper_limit", cell.cell_id
    return "", ""


def _row(time_value: float, current_value: float, pack: SeriesBatteryPack, source_v: float) -> dict[str, Any]:
    voltages = pack.cell_voltages(current_value)
    socs = pack.socs
    pack_voltage = float(sum(voltages))
    return {
        "time_s": float(time_value),
        "current_a": float(current_value),
        "source_voltage_v": source_v,
        "pack_voltage_v": pack_voltage,
        "pack_power_w": pack_voltage * float(current_value),
        "max_cell_voltage_v": float(max(voltages)),
        "min_cell_voltage_v": float(min(voltages)),
        "delta_cell_voltage_v": float(max(voltages) - min(voltages)),
        "max_soc": float(max(socs)),
        "min_soc": float(min(socs)),
        "delta_soc": float(max(socs) - min(socs)),
        "mean_soc": float(sum(socs) / len(socs)),
    }


def _run(pack: SeriesBatteryPack, current_function, duration_s: float, dt_s: float, load_type: str, load_value: float, data_source: str) -> dict[str, Any]:
    duration = float(duration_s)
    step = float(dt_s)
    if not math.isfinite(duration) or duration <= 0:
        raise PowerDeliveryError("仿真时长必须为正数")
    if not math.isfinite(step) or step <= 0:
        raise PowerDeliveryError("时间步长必须为正数")
    count = int(math.floor(duration / step + 1e-9))
    times = np.round(np.arange(count + 1, dtype=float) * step, 9)
    rows: list[dict[str, Any]] = []
    termination = "completed"
    termination_reason = ""
    termination_cell = ""
    termination_time = float(times[-1])

    for index, time_value in enumerate(times):
        source_v = effective_source_voltage_v(pack)
        try:
            current_value = float(current_function(pack, source_v))
        except PowerDeliveryError:
            termination = "infeasible"
            termination_reason = "load_operating_point_infeasible"
            termination_time = float(time_value)
            break
        if not math.isfinite(current_value):
            termination = "infeasible"
            termination_reason = "non_finite_current"
            termination_time = float(time_value)
            break
        rows.append(_row(float(time_value), current_value, pack, source_v))
        reason, cell_id = _termination_reason(pack, current_value)
        if reason:
            termination = "terminated"
            termination_reason = reason
            termination_cell = cell_id
            termination_time = float(time_value)
            break
        if index == len(times) - 1:
            break
        dt = float(times[index + 1] - times[index])
        for cell in pack.cells:
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
            cell.state = cell.state.with_updates(next_soc, next_voltages)

    frame = pd.DataFrame(rows)
    metadata = {
        "load_type": load_type,
        "load_value": float(load_value),
        "duration_requested_s": duration,
        "output_step_s": step,
        "points": int(len(frame)),
        "data_source": data_source,
        "assumption": "理想负载近似，未调用 PowerLab 真实 Buck 开关模型",
        "termination": termination,
        "termination_time_s": termination_time,
        "termination_reason": termination_reason,
        "termination_cell": termination_cell,
    }
    return {"frame": frame, "metadata": metadata}


def simulate_constant_resistance(
    pack: SeriesBatteryPack,
    resistance_ohm: float,
    duration_s: float,
    dt_s: float = 0.1,
    *,
    data_source: str = "custom_ecm_simulation",
) -> dict[str, Any]:
    """恒阻负载：I = Vpack / Rload，同时满足 Vpack = Ueff - I*Rtotal。"""
    resistance = float(resistance_ohm)
    if not math.isfinite(resistance) or resistance <= 0:
        raise PowerDeliveryError("负载电阻必须为正数")

    def current_function(model: SeriesBatteryPack, source_v: float) -> float:
        return source_v / (resistance + total_series_resistance_ohm(model))

    return _run(pack, current_function, duration_s, dt_s, "constant_resistance", resistance, data_source)


def simulate_constant_power(
    pack: SeriesBatteryPack,
    power_w: float,
    duration_s: float,
    dt_s: float = 0.1,
    *,
    data_source: str = "custom_ecm_simulation",
) -> dict[str, Any]:
    """理想恒功率负载：Ppack = Vpack * I，取正常高电压工作分支。"""
    power = float(power_w)
    if not math.isfinite(power) or power <= 0:
        raise PowerDeliveryError("负载功率必须为正数")

    def current_function(model: SeriesBatteryPack, source_v: float) -> float:
        resistance = total_series_resistance_ohm(model)
        if resistance <= 0.0:
            if source_v <= 0.0:
                raise PowerDeliveryError("电源电压非法")
            return power / source_v
        discriminant = source_v**2 - 4.0 * resistance * power
        if discriminant < 0.0:
            raise PowerDeliveryError("恒功率工作点判别式为负，负载不可行")
        voltage = (source_v + math.sqrt(discriminant)) / 2.0
        if voltage <= 0.0:
            raise PowerDeliveryError("恒功率端电压非法")
        return power / voltage

    return _run(pack, current_function, duration_s, dt_s, "constant_power", power, data_source)

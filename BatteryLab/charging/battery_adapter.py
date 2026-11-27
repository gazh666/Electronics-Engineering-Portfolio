"""电池适配层：统一电流方向、读取第三阶段冻结辨识模型、构造 3S 电芯组。

BatteryLab 前五阶段约定放电为正；本阶段控制器内部约定充电为正。
两者之间只允许通过本模块转换，禁止对全部电流直接取绝对值。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from battery_models.battery_pack import SeriesBatteryPack, build_inconsistent_pack
from identification.parameter_store import load_frozen_model

DEFAULT_MODEL_ID = "calce_sp2_25c_inr18650_20r_first_order_v1"

# 充电电压上下界与第五阶段保护阈值一致（不降低保护）。
CELL_LOWER_VOLTAGE_V = 2.8
CELL_UPPER_VOLTAGE_V = 4.25


class BatteryAdapterError(ValueError):
    """电池适配输入非法。"""


def to_ecm_current(charging_current_a: float) -> float:
    """控制器充电电流（流入电池为正）→ ECM 电流（放电为正）。"""
    if not math.isfinite(charging_current_a):
        raise ValueError("Invalid current")
    if charging_current_a < 0:
        raise ValueError("Expected positive charging current")
    return -charging_current_a


def to_charging_current(ecm_current_a: float) -> float:
    """ECM 电流 → 充电电流（允许负值表示放电）。"""
    if not math.isfinite(ecm_current_a):
        raise ValueError("Invalid current")
    return -ecm_current_a


def load_identified_battery_bundle(model_id: str | None = None) -> dict[str, Any]:
    """读取第三阶段冻结模型：参数、OCV 曲线与统一 ECM 定义。"""
    frozen = load_frozen_model(model_id or DEFAULT_MODEL_ID)
    parameters = frozen["parameters"]
    definition = parameters.as_definition(
        lower_voltage_v=CELL_LOWER_VOLTAGE_V,
        upper_voltage_v=CELL_UPPER_VOLTAGE_V,
    )
    return {
        "model_id": frozen["model_id"],
        "parameters": parameters,
        "definition": definition,
        "ocv_model": frozen["ocv_model"],
        "metadata": frozen["metadata"],
        "quality": frozen["quality"],
        "paths": frozen["paths"],
        "identified_soc_min": float(parameters.soc_min),
        "identified_soc_max": float(parameters.soc_max),
    }


def build_series_pack(
    bundle: dict[str, Any],
    socs: Sequence[float],
    *,
    capacities_ah: Sequence[float] | None = None,
    r0_ohm: Sequence[float] | None = None,
) -> SeriesBatteryPack:
    if not socs:
        raise BatteryAdapterError("至少需要一节电芯")
    if any(not 0.0 <= float(soc) <= 1.0 for soc in socs):
        raise BatteryAdapterError("SOC 必须位于 0 至 1")
    return build_inconsistent_pack(
        bundle["definition"],
        bundle["ocv_model"],
        socs=[float(soc) for soc in socs],
        capacities_ah=capacities_ah,
        r0_ohm=r0_ohm,
    )


def pack_ohmic_resistance_ohm(pack: SeriesBatteryPack) -> float:
    return float(sum(cell.parameters.r0_ohm for cell in pack.cells))


def cell_effective_voltage_v(cell: Any) -> float:
    """``OCV - Vp``：不含欧姆压降的电池内部等效电压。"""
    return float(cell.ocv_v() - sum(cell.state.polarization_voltages_v))


def pack_effective_voltage_v(pack: SeriesBatteryPack) -> float:
    """``Ueff = sum(OCV_i - Vp_i)``。"""
    return float(sum(cell_effective_voltage_v(cell) for cell in pack.cells))


def pack_port_voltage_v(pack: SeriesBatteryPack, charging_current_a: float) -> float:
    """真实电池组端电压（含欧姆与极化压降），输入为充电电流。"""
    return float(pack.pack_voltage(to_ecm_current(charging_current_a)))


def cell_terminal_voltages_v(pack: SeriesBatteryPack, charging_current_a: float) -> tuple[float, ...]:
    return pack.cell_voltages(to_ecm_current(charging_current_a))


def soc_validity(soc: float, identified_soc_min: float, identified_soc_max: float) -> str:
    """标注 SOC 是否落在第三阶段参数拟合区间内。"""
    if identified_soc_min <= soc <= identified_soc_max:
        return "IDENTIFIED_RANGE"
    if 0.0 <= soc <= 1.0:
        return "OCV_ENDPOINT_EXTRAPOLATED"
    return "OUT_OF_MODEL_DOMAIN"

"""电池状态定义与 SOC / 极化电压状态更新。

约定：时间 s、电流 A、容量 Ah、SOC 0-1。
放电电流为正，充电电流为负。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from battery_models.parameters import RCBranch

SECONDS_PER_HOUR = 3600.0


class StateError(ValueError):
    """状态或更新参数非法。"""


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise StateError(f"{name} 不允许使用布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StateError(f"{name} 必须是数值") from exc
    if not math.isfinite(number):
        raise StateError(f"{name} 必须是有限数值")
    return number


@dataclass(frozen=True)
class CellState:
    """单体状态：SOC 与各 RC 支路极化电压。"""

    soc: float
    polarization_voltages_v: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        soc = _finite(self.soc, "SOC")
        if not 0.0 <= soc <= 1.0:
            raise StateError("SOC 必须位于 0 至 1")
        voltages = tuple(_finite(value, f"极化电压[{index}]") for index, value in enumerate(self.polarization_voltages_v))
        object.__setattr__(self, "soc", soc)
        object.__setattr__(self, "polarization_voltages_v", voltages)

    @classmethod
    def initial(cls, soc: float, order: int = 0, initial_polarization_v: float = 0.0) -> "CellState":
        if order not in (0, 1, 2):
            raise StateError("RC 支路数量必须为 0、1 或 2")
        return cls(soc=soc, polarization_voltages_v=tuple([float(initial_polarization_v)] * order))

    def with_updates(self, soc: float, voltages: Sequence[float]) -> "CellState":
        return CellState(soc=soc, polarization_voltages_v=tuple(voltages))


def update_soc(
    soc: float,
    current_a: float,
    dt_s: float,
    capacity_ah: float,
    charge_efficiency: float = 1.0,
    discharge_efficiency: float = 1.0,
) -> float:
    """按零阶保持电流更新 SOC。

    放电时有效电荷消耗为 ``I * dt / eta_discharge``；
    充电时有效电荷增加为 ``-I * dt * eta_charge``。
    本函数不做静默截断，越界由求解器定位终止事件。
    """
    soc_value = _finite(soc, "SOC")
    if not 0.0 <= soc_value <= 1.0:
        raise StateError("SOC 必须位于 0 至 1")
    current = _finite(current_a, "电流")
    dt = _finite(dt_s, "时间步长")
    capacity = _finite(capacity_ah, "额定容量")
    eta_charge = _finite(charge_efficiency, "充电库仑效率")
    eta_discharge = _finite(discharge_efficiency, "放电库仑效率")
    if dt <= 0.0:
        raise StateError("时间步长必须为正数")
    if capacity <= 0.0:
        raise StateError("额定容量必须为正数")
    if not 0.0 < eta_charge <= 1.0 or not 0.0 < eta_discharge <= 1.0:
        raise StateError("库仑效率必须位于 (0, 1]")

    if current >= 0.0:
        effective_current = current / eta_discharge
    else:
        effective_current = current * eta_charge
    return soc_value - effective_current * dt / (SECONDS_PER_HOUR * capacity)


def update_polarization_voltage(
    previous_voltage_v: float,
    current_a: float,
    resistance_ohm: float,
    capacitance_f: float,
    dt_s: float,
) -> float:
    """单个 RC 支路在恒定电流下的精确离散更新。

    ``V_next = V * exp(-dt/tau) + I * R * (1 - exp(-dt/tau))``，
    使用 ``expm1`` 保证极小步长时的数值精度。
    """
    previous = _finite(previous_voltage_v, "极化电压")
    current = _finite(current_a, "电流")
    resistance = _finite(resistance_ohm, "RC 电阻")
    capacitance = _finite(capacitance_f, "RC 电容")
    dt = _finite(dt_s, "时间步长")
    if resistance <= 0.0 or capacitance <= 0.0:
        raise StateError("RC 电阻与电容必须为正数")
    if dt <= 0.0:
        raise StateError("时间步长必须为正数")
    tau = resistance * capacitance
    decay = math.exp(-dt / tau)
    one_minus_decay = -math.expm1(-dt / tau)
    return previous * decay + current * resistance * one_minus_decay


def update_branch_voltages(
    previous_voltages: Sequence[float],
    branches: Sequence[RCBranch],
    current_a: float,
    dt_s: float,
) -> tuple[float, ...]:
    """按支路列表批量更新极化电压，复用同一精确更新函数。"""
    if len(previous_voltages) != len(branches):
        raise StateError("极化电压数量与 RC 支路数量不一致")
    return tuple(
        update_polarization_voltage(voltage, current_a, branch.resistance_ohm, branch.capacitance_f, dt_s)
        for voltage, branch in zip(previous_voltages, branches)
    )


def branch_stored_energy_j(branches: Sequence[RCBranch], voltages: Sequence[float]) -> tuple[float, ...]:
    """各 RC 电容储能 ``0.5 * C * V^2``。"""
    if len(branches) != len(voltages):
        raise StateError("极化电压数量与 RC 支路数量不一致")
    return tuple(0.5 * branch.capacitance_f * float(voltage) ** 2 for branch, voltage in zip(branches, voltages))


def branch_dissipation_w(branches: Sequence[RCBranch], voltages: Sequence[float]) -> tuple[float, ...]:
    """各极化电阻瞬时损耗 ``V^2 / R``（不是 ``I^2 * R``）。"""
    if len(branches) != len(voltages):
        raise StateError("极化电压数量与 RC 支路数量不一致")
    return tuple(float(voltage) ** 2 / branch.resistance_ohm for branch, voltage in zip(branches, voltages))

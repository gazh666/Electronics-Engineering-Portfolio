"""充电能量与电量积分：梯形法与零阶保持（ZOH）双口径。

为什么保留两种口径：
- 开关级波形在一个 PWM 周期内剧烈变化，梯形法在周期边界会引入与采样相位相关的偏差；
- ZOH（右端矩形）与数字控制器/能量表常用的求和口径一致。
两种结果的差异本身就是一个可报告的不确定度来源，不允许只挑好看的那个。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


def _as_series(name: str, values: Any, expected: int) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} 必须是一维序列")
    if array.size != expected:
        raise ValueError(f"{name} 长度 {array.size} 与时间轴 {expected} 不一致")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} 含非有限值")
    return array


def _as_time(time_s: Any) -> np.ndarray:
    t = np.asarray(time_s, dtype=float)
    if t.ndim != 1 or t.size < 2:
        raise ValueError("时间轴至少需要 2 个点")
    if not np.all(np.isfinite(t)):
        raise ValueError("时间轴含非有限值")
    if not np.all(np.diff(t) > 0.0):
        raise ValueError("时间轴必须严格递增")
    return t


def integrate_trapezoid(values: Any, time_s: Any) -> float:
    t = _as_time(time_s)
    y = _as_series("values", values, t.size)
    integrate = getattr(np, "trapezoid", None)
    if integrate is None:  # numpy < 2.0
        integrate = np.trapz
    return float(integrate(y, t))


def integrate_zoh(values: Any, time_s: Any) -> float:
    """零阶保持积分：``sum(y[i] * (t[i+1] - t[i]))``。"""
    t = _as_time(time_s)
    y = _as_series("values", values, t.size)
    return float(np.sum(y[:-1] * np.diff(t)))


@dataclass(frozen=True)
class EnergySummary:
    duration_s: float
    net_charge_ah: float
    reverse_charge_ah: float
    battery_energy_j: float
    battery_energy_wh: float
    input_energy_j: float | None
    input_energy_wh: float | None
    energy_efficiency_percent: float | None
    integration_gap_percent: float | None
    method: str = "zoh_primary_trapezoid_crosscheck"

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_s": self.duration_s,
            "net_charge_ah": self.net_charge_ah,
            "reverse_charge_ah": self.reverse_charge_ah,
            "battery_energy_j": self.battery_energy_j,
            "battery_energy_wh": self.battery_energy_wh,
            "input_energy_j": self.input_energy_j,
            "input_energy_wh": self.input_energy_wh,
            "energy_efficiency_percent": self.energy_efficiency_percent,
            "integration_gap_percent": self.integration_gap_percent,
            "method": self.method,
        }


def calculate_charging_energy(
    time_s: Any,
    pack_voltage_v: Any,
    charging_current_a: Any,
    input_voltage_v: Any = None,
    input_current_a: Any = None,
) -> EnergySummary:
    """积分电池侧与输入端能量。

    ``charging_current_a`` 采用充电为正的约定；负值计为反向（放电）电量，
    不会被取绝对值，也不会被静默丢弃。
    """
    t = _as_time(time_s)
    vbat = _as_series("pack_voltage_v", pack_voltage_v, t.size)
    ibat = _as_series("charging_current_a", charging_current_a, t.size)

    p_bat = vbat * ibat
    battery_energy_zoh = integrate_zoh(p_bat, t)
    battery_energy_trap = integrate_trapezoid(p_bat, t)

    if abs(battery_energy_trap) > 0.0:
        gap = 100.0 * abs(battery_energy_zoh - battery_energy_trap) / abs(battery_energy_trap)
    else:
        gap = None

    net_charge_ah = integrate_zoh(ibat, t) / 3600.0
    negative = np.where(ibat < 0.0, ibat, 0.0)
    reverse_charge_ah = abs(integrate_zoh(negative, t)) / 3600.0

    input_energy_j: float | None = None
    input_energy_wh: float | None = None
    efficiency: float | None = None
    if input_voltage_v is not None and input_current_a is not None:
        vin = _as_series("input_voltage_v", input_voltage_v, t.size)
        iin = _as_series("input_current_a", input_current_a, t.size)
        input_energy_j = integrate_zoh(vin * iin, t)
        input_energy_wh = input_energy_j / 3600.0
        if input_energy_j <= 0.0:
            raise ValueError("输入能量必须为正，检查输入端功率符号")
        efficiency = 100.0 * battery_energy_zoh / input_energy_j
    elif input_voltage_v is not None or input_current_a is not None:
        raise ValueError("输入电压与输入电流必须同时提供")

    for name, value in (
        ("battery_energy_j", battery_energy_zoh),
        ("net_charge_ah", net_charge_ah),
    ):
        if not math.isfinite(value):
            raise ValueError(f"积分结果非有限: {name}")

    return EnergySummary(
        duration_s=float(t[-1] - t[0]),
        net_charge_ah=net_charge_ah,
        reverse_charge_ah=reverse_charge_ah,
        battery_energy_j=battery_energy_zoh,
        battery_energy_wh=battery_energy_zoh / 3600.0,
        input_energy_j=input_energy_j,
        input_energy_wh=input_energy_wh,
        energy_efficiency_percent=efficiency,
        integration_gap_percent=gap,
    )

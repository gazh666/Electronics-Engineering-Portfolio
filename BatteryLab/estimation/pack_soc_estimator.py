"""3S 单体 SOC 估计（Task 29 / Task 30）。

串联电池组电流关系：

```text
未均衡：  I_cell_i = I_pack
被动均衡：I_cell_i = I_pack + I_balance_i     （I_balance_i ≥ 0，向该节泄放）
```

约定放电为正、充电为负，与 ECM / 安时积分一致。被动均衡在单体上额外消耗
电流，因此该节 SOC 下降更快；若忽略均衡电流，该节 SOC 会被系统性高估。

重要：3S 电池组的可用容量受最弱电芯限制，**不能把三节剩余 Ah 直接相加**。
``summarize_pack_soc`` 给出的 ``ideal_discharge_charge_bound_ah`` 只是理想
边界，不是电池组实际可用容量。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from estimation.coulomb_counter import CoulombCounter
from estimation.ecm_observer import ECMObserver, ObserverRCBranch


class PackEstimationError(ValueError):
    """电池组估计输入非法。"""


def calculate_cell_currents(
    pack_current_a: float,
    balancing_currents_a: Sequence[float],
) -> np.ndarray:
    """由电池组电流与各节均衡电流计算单体电流。"""
    balancing = np.asarray(balancing_currents_a, dtype=float)
    if balancing.ndim != 1:
        raise PackEstimationError("Invalid current array")
    if not math.isfinite(float(pack_current_a)):
        raise PackEstimationError("Invalid pack current")
    if not np.isfinite(balancing).all():
        raise PackEstimationError("Invalid balancing current")
    if np.any(balancing < 0.0):
        raise PackEstimationError("Expected passive balancing currents")
    return float(pack_current_a) + balancing


def summarize_pack_soc(
    cell_soc: Sequence[float],
    capacities_ah: Sequence[float],
) -> dict[str, float]:
    """电池组 SOC 描述性统计与理想剩余电荷边界。"""
    soc = np.asarray(cell_soc, dtype=float)
    capacities = np.asarray(capacities_ah, dtype=float)
    if soc.ndim != 1 or capacities.ndim != 1 or soc.shape != capacities.shape or soc.size == 0:
        raise PackEstimationError("Invalid pack state")
    if not (np.isfinite(soc).all() and np.isfinite(capacities).all()):
        raise PackEstimationError("Invalid pack state")
    if np.any((soc < 0.0) | (soc > 1.0)):
        raise PackEstimationError("Invalid SOC")
    if np.any(capacities <= 0.0):
        raise PackEstimationError("Invalid capacity")

    remaining_charge = soc * capacities
    available_charge_room = (1.0 - soc) * capacities
    return {
        "mean_soc": float(np.mean(soc)),
        "capacity_weighted_mean_soc": float(np.sum(remaining_charge) / np.sum(capacities)),
        "minimum_cell_soc": float(np.min(soc)),
        "maximum_cell_soc": float(np.max(soc)),
        "soc_spread_pp": float((np.max(soc) - np.min(soc)) * 100.0),
        "ideal_discharge_charge_bound_ah": float(np.min(remaining_charge)),
        "ideal_charge_room_bound_ah": float(np.min(available_charge_room)),
    }


@dataclass
class PackSOCEstimator:
    """逐节独立安时积分（可选逐节 ECM 电压校正）的电池组估计器。"""

    capacities_ah: Sequence[float]
    initial_socs: Sequence[float]
    charge_efficiency: float = 1.0
    discharge_efficiency: float = 1.0
    r0_ohm: Sequence[float] | None = None
    branches: tuple[ObserverRCBranch, ...] | None = None
    ocv_tables: Sequence[Any] | None = None
    correction_time_constant_s: float = 120.0
    minimum_ocv_slope: float = 0.2
    maximum_correction_rate: float = 0.001
    counters: list[CoulombCounter] = field(default_factory=list, init=False)
    observers: list[ECMObserver] | None = field(default=None, init=False)
    last_cell_currents: np.ndarray | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        capacities = [float(value) for value in self.capacities_ah]
        socs = [float(value) for value in self.initial_socs]
        if len(capacities) != len(socs) or not capacities:
            raise PackEstimationError("容量与初始 SOC 长度必须一致且非空")
        if any(value <= 0.0 for value in capacities):
            raise PackEstimationError("容量必须为正")
        if any(not 0.0 <= value <= 1.0 for value in socs):
            raise PackEstimationError("初始 SOC 必须位于 0 至 1")
        self.capacities_ah = capacities
        self.initial_socs = socs

        self.counters = [
            CoulombCounter(
                capacity_ah=capacity,
                soc=soc,
                charge_efficiency=self.charge_efficiency,
                discharge_efficiency=self.discharge_efficiency,
            )
            for capacity, soc in zip(capacities, socs)
        ]

        self.observers = None
        if self.r0_ohm is not None or self.branches is not None or self.ocv_tables is not None:
            if self.r0_ohm is None or self.branches is None or self.ocv_tables is None:
                raise PackEstimationError("启用电压校正时 R0、RC 支路与 OCV 表必须同时提供")
            if len(self.r0_ohm) != len(capacities) or len(self.ocv_tables) != len(capacities):
                raise PackEstimationError("逐节参数长度不一致")
            self.observers = [
                ECMObserver(
                    counter=counters,
                    r0_ohm=float(r0),
                    branches=tuple(self.branches),
                    ocv_model=table,
                    correction_time_constant_s=self.correction_time_constant_s,
                    minimum_ocv_slope=self.minimum_ocv_slope,
                    maximum_correction_rate=self.maximum_correction_rate,
                )
                for counters, r0, table in zip(self.counters, self.r0_ohm, self.ocv_tables)
            ]

    @property
    def cell_socs(self) -> np.ndarray:
        return np.asarray([counter.soc for counter in self.counters], dtype=float)

    def step(
        self,
        previous_pack_current_a: float,
        pack_current_a: float,
        dt_s: float,
        balancing_currents_a: Sequence[float] | None = None,
        cell_voltages_v: Sequence[float] | None = None,
    ) -> dict[str, Any]:
        """推进一个时间步，返回逐节 SOC、电流与电池组摘要。"""
        if not math.isfinite(float(previous_pack_current_a)) or not math.isfinite(float(pack_current_a)):
            raise PackEstimationError("电池组电流非法")
        if not math.isfinite(float(dt_s)) or float(dt_s) <= 0.0:
            raise PackEstimationError("时间步必须为正")

        if balancing_currents_a is None:
            balancing = np.zeros(len(self.counters), dtype=float)
        else:
            balancing = np.asarray(balancing_currents_a, dtype=float)
            if balancing.shape != (len(self.counters),):
                raise PackEstimationError("均衡电流长度与电芯数量不一致")

        interval_cell_currents = calculate_cell_currents(previous_pack_current_a, balancing)
        instant_cell_currents = calculate_cell_currents(pack_current_a, balancing)

        cell_soc: list[float] = []
        cell_status: list[str] = []
        residuals: list[float | None] = []

        if self.observers is not None and cell_voltages_v is not None:
            voltages = [float(value) for value in cell_voltages_v]
            if len(voltages) != len(self.observers):
                raise PackEstimationError("单体电压数量与电芯数量不一致")
            for observer, previous_current, current, voltage in zip(
                self.observers, interval_cell_currents, instant_cell_currents, voltages
            ):
                result = observer.step(
                    previous_current_a=float(previous_current),
                    current_a=float(current),
                    measured_voltage_v=float(voltage),
                    dt_s=float(dt_s),
                    allow_voltage_correction=math.isfinite(float(voltage)),
                )
                cell_soc.append(result.soc)
                cell_status.append(result.status)
                residuals.append(result.residual_v)
        else:
            for counter, previous_current in zip(self.counters, interval_cell_currents):
                update = counter.step(float(previous_current), float(dt_s))
                cell_soc.append(update.soc)
                cell_status.append(update.status)
                residuals.append(None)

        self.last_cell_currents = instant_cell_currents
        summary = summarize_pack_soc(cell_soc, self.capacities_ah)
        return {
            "cell_soc": cell_soc,
            "cell_currents_a": [float(value) for value in instant_cell_currents],
            "cell_status": cell_status,
            "cell_residual_v": residuals,
            "summary": summary,
        }

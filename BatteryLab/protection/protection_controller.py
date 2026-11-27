"""保护控制器：把单体电压、组端电流与温度变成真实的充放电许可。

所有阈值来自 ``protection/limits.py``，所有判决经过比较器（迟滞 + 确认延时），
所有结果进入锁存状态机。控制器不直接"相信"配置值：它输出的是比较器过滤后的
许可，供后续阶段（第六阶段充电器）作为独立 BMS 保护接口。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from protection.balancing import BalanceChannel, PassiveBalancer
from protection.comparator import ComparatorConfig, HysteresisComparator
from protection.limits import ProtectionLimits
from protection.state_machine import (
    FaultCode,
    ProtectionState,
    ProtectionStateMachine,
)

# 主回路电流超过该值时视为正在放电，不启动均衡。
BALANCING_DISCHARGE_THRESHOLD_A = 0.05


class ProtectionControllerError(ValueError):
    """保护控制器输入非法。"""


@dataclass(frozen=True)
class ProtectionSnapshot:
    """一次保护判决的完整结果。"""

    time_s: float
    cell_voltages_v: tuple[float, ...]
    pack_voltage_v: float
    pack_current_a: float
    maximum_cell_voltage_v: float
    minimum_cell_voltage_v: float
    delta_cell_voltage_v: float
    temperature_c: float
    measurement_valid: bool
    state: ProtectionState
    charge_allowed: bool
    discharge_allowed: bool
    charge_fet_enabled: bool
    discharge_fet_enabled: bool
    active_faults: tuple[str, ...]
    latched_faults: tuple[str, ...]
    balancing: tuple[BalanceChannel, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_s": self.time_s,
            "cell_voltages_v": list(self.cell_voltages_v),
            "pack_voltage_v": self.pack_voltage_v,
            "pack_current_a": self.pack_current_a,
            "maximum_cell_voltage_v": self.maximum_cell_voltage_v,
            "minimum_cell_voltage_v": self.minimum_cell_voltage_v,
            "delta_cell_voltage_v": self.delta_cell_voltage_v,
            "temperature_c": self.temperature_c,
            "measurement_valid": self.measurement_valid,
            "state": self.state.value,
            "charge_allowed": self.charge_allowed,
            "discharge_allowed": self.discharge_allowed,
            "charge_fet_enabled": self.charge_fet_enabled,
            "discharge_fet_enabled": self.discharge_fet_enabled,
            "active_faults": list(self.active_faults),
            "latched_faults": list(self.latched_faults),
            "balancing": [channel.to_dict() for channel in self.balancing],
        }


@dataclass
class ProtectionController:
    """带逐节比较器、锁存状态机与被动均衡决策的保护控制器。"""

    limits: ProtectionLimits
    cell_ids: tuple[str, ...]
    state_machine: ProtectionStateMachine
    balancer: PassiveBalancer
    overvoltage: dict[str, HysteresisComparator] = field(default_factory=dict)
    undervoltage: dict[str, HysteresisComparator] = field(default_factory=dict)
    charge_overcurrent: HysteresisComparator | None = None
    discharge_overcurrent: HysteresisComparator | None = None
    short_circuit: HysteresisComparator | None = None
    over_temperature: HysteresisComparator | None = None
    charge_high_temperature: HysteresisComparator | None = None
    charge_low_temperature: HysteresisComparator | None = None
    history: list[ProtectionSnapshot] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        limits: ProtectionLimits,
        cell_ids: Sequence[str],
        *,
        state_machine: ProtectionStateMachine | None = None,
    ) -> "ProtectionController":
        ids = tuple(str(cell_id) for cell_id in cell_ids)
        if not ids:
            raise ProtectionControllerError("至少需要一节电芯")
        if len(set(ids)) != len(ids):
            raise ProtectionControllerError("电芯编号必须唯一")
        overvoltage = {
            cell_id: HysteresisComparator(
                ComparatorConfig(
                    name=f"OV_{cell_id}",
                    threshold=limits.cell_overvoltage_trip_v,
                    hysteresis=limits.cell_overvoltage_trip_v - limits.cell_overvoltage_release_v,
                    confirmation_delay_s=limits.overvoltage_delay_s,
                    propagation_delay_s=limits.comparator_propagation_delay_s,
                    direction="high",
                )
            )
            for cell_id in ids
        }
        undervoltage = {
            cell_id: HysteresisComparator(
                ComparatorConfig(
                    name=f"UV_{cell_id}",
                    threshold=limits.cell_undervoltage_trip_v,
                    hysteresis=limits.cell_undervoltage_release_v - limits.cell_undervoltage_trip_v,
                    confirmation_delay_s=limits.undervoltage_delay_s,
                    propagation_delay_s=limits.comparator_propagation_delay_s,
                    direction="low",
                )
            )
            for cell_id in ids
        }
        machine = state_machine or ProtectionStateMachine(
            all_clear_hold_s=limits.all_clear_hold_s,
            require_measurement_valid=True,
        )
        return cls(
            limits=limits,
            cell_ids=ids,
            state_machine=machine,
            balancer=PassiveBalancer(limits),
            overvoltage=overvoltage,
            undervoltage=undervoltage,
            charge_overcurrent=HysteresisComparator(
                ComparatorConfig(
                    name="CHARGE_OVERCURRENT",
                    threshold=limits.charge_overcurrent_trip_a,
                    hysteresis=limits.charge_overcurrent_trip_a - limits.charge_overcurrent_release_a,
                    confirmation_delay_s=limits.charge_overcurrent_delay_s,
                    propagation_delay_s=limits.comparator_propagation_delay_s,
                    direction="high",
                )
            ),
            discharge_overcurrent=HysteresisComparator(
                ComparatorConfig(
                    name="DISCHARGE_OVERCURRENT",
                    threshold=limits.discharge_overcurrent_trip_a,
                    hysteresis=limits.discharge_overcurrent_trip_a - limits.discharge_overcurrent_release_a,
                    confirmation_delay_s=limits.discharge_overcurrent_delay_s,
                    propagation_delay_s=limits.comparator_propagation_delay_s,
                    direction="high",
                )
            ),
            short_circuit=HysteresisComparator(
                ComparatorConfig(
                    name="SHORT_CIRCUIT",
                    threshold=limits.short_circuit_trip_a,
                    hysteresis=limits.short_circuit_trip_a - limits.short_circuit_release_a,
                    confirmation_delay_s=limits.short_circuit_delay_s,
                    propagation_delay_s=limits.comparator_propagation_delay_s,
                    direction="high",
                )
            ),
            over_temperature=HysteresisComparator(
                ComparatorConfig(
                    name="OVER_TEMPERATURE",
                    threshold=limits.over_temperature_trip_c,
                    hysteresis=limits.over_temperature_trip_c - limits.over_temperature_release_c,
                    confirmation_delay_s=limits.over_temperature_delay_s,
                    propagation_delay_s=limits.comparator_propagation_delay_s,
                    direction="high",
                )
            ),
            charge_high_temperature=HysteresisComparator(
                ComparatorConfig(
                    name="CHARGE_HIGH_TEMPERATURE",
                    threshold=limits.charge_temperature_max_c,
                    hysteresis=limits.temperature_release_margin_c,
                    confirmation_delay_s=limits.over_temperature_delay_s,
                    propagation_delay_s=limits.comparator_propagation_delay_s,
                    direction="high",
                )
            ),
            charge_low_temperature=HysteresisComparator(
                ComparatorConfig(
                    name="UNDER_TEMPERATURE_CHARGE",
                    threshold=limits.charge_temperature_min_c,
                    hysteresis=limits.temperature_release_margin_c,
                    confirmation_delay_s=limits.under_temperature_delay_s,
                    propagation_delay_s=limits.comparator_propagation_delay_s,
                    direction="low",
                )
            ),
        )

    def arm(self, time_s: float = 0.0) -> None:
        self.state_machine.arm(time_s)

    def request_recovery(self, time_s: float) -> bool:
        return self.state_machine.request_recovery(time_s)

    def update(
        self,
        time_s: float,
        cell_voltages_v: Sequence[float],
        pack_current_a: float,
        temperature_c: float,
        *,
        measurement_valid: bool = True,
        measurement_time_s: float | None = None,
    ) -> ProtectionSnapshot:
        if len(cell_voltages_v) != len(self.cell_ids):
            raise ProtectionControllerError("单体电压数量与电芯数量不一致")
        now = float(time_s)
        if not math.isfinite(now):
            raise ProtectionControllerError("时间必须是有限数值")
        voltages = tuple(float(value) for value in cell_voltages_v)
        if any(not math.isfinite(value) for value in voltages):
            measurement_valid = False
        current = float(pack_current_a)
        temperature = float(temperature_c)
        if not math.isfinite(current) or not math.isfinite(temperature):
            measurement_valid = False
        if measurement_time_s is not None:
            age = now - float(measurement_time_s)
            if age > self.limits.measurement_max_age_s:
                measurement_valid = False

        # 测量无效时不更新比较器内部状态，直接由状态机锁存。
        if measurement_valid:
            for cell_id, voltage in zip(self.cell_ids, voltages):
                self.overvoltage[cell_id].step(voltage, now)
                self.undervoltage[cell_id].step(voltage, now)
            charge_current = max(-current, 0.0)
            assert self.charge_overcurrent is not None
            assert self.discharge_overcurrent is not None
            assert self.short_circuit is not None
            assert self.over_temperature is not None
            assert self.charge_high_temperature is not None
            assert self.charge_low_temperature is not None
            self.charge_overcurrent.step(charge_current, now)
            self.discharge_overcurrent.step(max(current, 0.0), now)
            self.short_circuit.step(abs(current), now)
            self.over_temperature.step(temperature, now)
            self.charge_high_temperature.step(temperature, now)
            self.charge_low_temperature.step(temperature, now)

        active: dict[FaultCode, str | None] = {}
        for cell_id, voltage in zip(self.cell_ids, voltages):
            if self.overvoltage[cell_id].output:
                active[FaultCode.CELL_OVERVOLTAGE] = f"{cell_id}:{voltage:.4f}V"
            if self.undervoltage[cell_id].output:
                active[FaultCode.CELL_UNDERVOLTAGE] = f"{cell_id}:{voltage:.4f}V"
        if self.charge_overcurrent is not None and self.charge_overcurrent.output:
            active[FaultCode.CHARGE_OVERCURRENT] = f"{max(-current, 0.0):.4f}A"
        if self.discharge_overcurrent is not None and self.discharge_overcurrent.output:
            active[FaultCode.DISCHARGE_OVERCURRENT] = f"{max(current, 0.0):.4f}A"
        if self.short_circuit is not None and self.short_circuit.output:
            active[FaultCode.SHORT_CIRCUIT] = f"{abs(current):.4f}A"
        if self.over_temperature is not None and self.over_temperature.output:
            active[FaultCode.OVER_TEMPERATURE] = f"{temperature:.2f}C"
        if self.charge_high_temperature is not None and self.charge_high_temperature.output:
            active[FaultCode.CHARGE_HIGH_TEMPERATURE] = f"{temperature:.2f}C"
        if self.charge_low_temperature is not None and self.charge_low_temperature.output:
            active[FaultCode.UNDER_TEMPERATURE_CHARGE] = f"{temperature:.2f}C"

        self.state_machine.update(now, active, measurement_valid)

        charge_allowed = self.state_machine.charge_allowed
        discharge_allowed = self.state_machine.discharge_allowed
        balancing_permitted = (
            self.state_machine.balancing_allowed
            and abs(current) <= BALANCING_DISCHARGE_THRESHOLD_A
        )
        channels = (
            self.balancer.plan(self.cell_ids, voltages, permitted=balancing_permitted)
            if measurement_valid
            else tuple()
        )

        snapshot = ProtectionSnapshot(
            time_s=now,
            cell_voltages_v=voltages,
            pack_voltage_v=float(sum(voltages)),
            pack_current_a=current,
            maximum_cell_voltage_v=float(max(voltages)),
            minimum_cell_voltage_v=float(min(voltages)),
            delta_cell_voltage_v=float(max(voltages) - min(voltages)),
            temperature_c=temperature,
            measurement_valid=measurement_valid,
            state=self.state_machine.state,
            charge_allowed=charge_allowed,
            discharge_allowed=discharge_allowed,
            charge_fet_enabled=charge_allowed,
            discharge_fet_enabled=discharge_allowed,
            active_faults=tuple(sorted(code.value for code in active)),
            latched_faults=self.state_machine.latched_codes,
            balancing=tuple(channels),
        )
        self.history.append(snapshot)
        return snapshot

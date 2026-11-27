"""被动均衡：支路电流、功耗、温升与三节不一致性收敛。

均衡电阻与 MOSFET 串联跨接在单体两端，把高电压单体的电荷以热的形式耗散。
本模块给出解析均衡电流/功率，并在冻结 ECM 上按真实电荷积分更新各节 SOC，
用于验证"不一致性是否真的收敛"，而不是只画一条下降曲线。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from battery_models.battery_pack import PackCellModel
from protection.limits import ProtectionLimits


class BalancingError(ValueError):
    """均衡输入非法。"""


@dataclass(frozen=True)
class BalanceChannel:
    """单节均衡通道的瞬时状态。"""

    cell_id: str
    cell_voltage_v: float
    enabled: bool
    current_a: float
    power_w: float
    temperature_rise_c: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "cell_voltage_v": self.cell_voltage_v,
            "enabled": self.enabled,
            "current_a": self.current_a,
            "power_w": self.power_w,
            "temperature_rise_c": self.temperature_rise_c,
            "reason": self.reason,
        }


def balance_branch_current(cell_voltage_v: float, resistor_ohm: float, mosfet_rds_on_ohm: float) -> float:
    """均衡支路电流 I = Vcell / (Rbal + Rds_on)。"""
    for value, name in ((cell_voltage_v, "cell_voltage_v"), (resistor_ohm, "resistor_ohm"), (mosfet_rds_on_ohm, "mosfet_rds_on_ohm")):
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise BalancingError(f"{name} 必须是有限数值")
    total = float(resistor_ohm) + float(mosfet_rds_on_ohm)
    if total <= 0.0:
        raise BalancingError("均衡支路总电阻必须为正")
    if float(cell_voltage_v) < 0.0:
        raise BalancingError("单体电压不能为负")
    return float(cell_voltage_v) / total


def balance_branch_power(current_a: float, resistor_ohm: float, mosfet_rds_on_ohm: float) -> float:
    return float(current_a) ** 2 * (float(resistor_ohm) + float(mosfet_rds_on_ohm))


@dataclass
class PassiveBalancer:
    """带启动/停止回差与最大同时节数限制的被动均衡决策器。"""

    limits: ProtectionLimits
    active: dict[str, bool] = field(default_factory=dict)

    def _thresholds(self) -> tuple[float, float, float]:
        return (
            self.limits.balance_start_cell_voltage_v,
            self.limits.balance_start_delta_v,
            self.limits.balance_stop_delta_v,
        )

    def plan(
        self,
        cell_ids: Sequence[str],
        cell_voltages_v: Sequence[float],
        *,
        permitted: bool,
        ambient_temperature_c: float | None = None,
    ) -> list[BalanceChannel]:
        if len(cell_ids) != len(cell_voltages_v) or not cell_ids:
            raise BalancingError("电芯编号与电压长度必须一致且非空")
        voltages = [float(value) for value in cell_voltages_v]
        if any(not math.isfinite(value) or value < 0.0 for value in voltages):
            raise BalancingError("单体电压必须是有限非负值")
        ambient = (
            self.limits.balance_ambient_temperature_c
            if ambient_temperature_c is None
            else float(ambient_temperature_c)
        )
        start_voltage, start_delta, stop_delta = self._thresholds()
        delta = max(voltages) - min(voltages)
        minimum = min(voltages)
        maximum = max(voltages)
        in_progress = any(self.active.values())

        # 启动条件：最高单体达到启动电压且压差达到启动回差。
        # 一旦开始，允许持续到压差降到停止回差；每一步都重新选择当前最高单体，
        # 避免把已经不高的单体继续放电。
        started = permitted and delta >= start_delta and maximum >= start_voltage
        continuing = (
            permitted
            and in_progress
            and delta > stop_delta
            and maximum > self.limits.cell_undervoltage_release_v
        )
        allow = started or continuing

        candidates: list[tuple[int, str, float]] = []
        if allow:
            for index, (cell_id, voltage) in enumerate(zip(cell_ids, voltages)):
                if (voltage - minimum) > stop_delta:
                    candidates.append((index, cell_id, voltage))

        # 同时均衡节数受限，优先最高电压单体。
        candidates.sort(key=lambda item: item[2], reverse=True)
        allowed = {cell_id for _, cell_id, _ in candidates[: self.limits.balance_max_simultaneous_cells]}

        channels: list[BalanceChannel] = []
        for cell_id, voltage in zip(cell_ids, voltages):
            enabled = cell_id in allowed
            self.active[cell_id] = enabled
            if not permitted:
                reason = "BALANCE_NOT_PERMITTED"
            elif not enabled:
                reason = "BELOW_START_CONDITION"
            else:
                reason = "BALANCING"
            current = (
                balance_branch_current(
                    voltage, self.limits.balance_resistor_ohm, self.limits.balance_mosfet_rds_on_ohm
                )
                if enabled
                else 0.0
            )
            power = (
                balance_branch_power(
                    current, self.limits.balance_resistor_ohm, self.limits.balance_mosfet_rds_on_ohm
                )
                if enabled
                else 0.0
            )
            rise = power * self.limits.balance_resistor_thermal_resistance_c_per_w if enabled else 0.0
            channels.append(
                BalanceChannel(
                    cell_id=cell_id,
                    cell_voltage_v=voltage,
                    enabled=enabled,
                    current_a=current,
                    power_w=power,
                    temperature_rise_c=rise,
                    reason=reason,
                )
            )
        return channels

    def resistor_temperature_c(self, power_w: float, ambient_c: float | None = None) -> float:
        ambient = (
            self.limits.balance_ambient_temperature_c if ambient_c is None else float(ambient_c)
        )
        return ambient + float(power_w) * self.limits.balance_resistor_thermal_resistance_c_per_w

    def check_resistor_power(self, power_w: float) -> bool:
        """返回 True 表示超过电阻额定功率。"""
        return float(power_w) > self.limits.balance_resistor_power_rating_w


@dataclass(frozen=True)
class BalancingRunResult:
    time_s: list[float]
    pack_voltage_v: list[float]
    max_cell_voltage_v: list[float]
    min_cell_voltage_v: list[float]
    delta_cell_voltage_v: list[float]
    cell_soc: dict[str, list[float]]
    cell_voltage: dict[str, list[float]]
    balance_current: dict[str, list[float]]
    energy_dissipated_wh: float
    peak_resistor_power_w: float
    peak_resistor_temperature_c: float
    initial_delta_v: float
    final_delta_v: float
    delta_reduction_fraction: float
    time_to_stop_s: float | None
    events: list[dict[str, Any]]

    def summary(self) -> dict[str, Any]:
        return {
            "initial_delta_v": self.initial_delta_v,
            "final_delta_v": self.final_delta_v,
            "delta_reduction_fraction": self.delta_reduction_fraction,
            "energy_dissipated_wh": self.energy_dissipated_wh,
            "peak_resistor_power_w": self.peak_resistor_power_w,
            "peak_resistor_temperature_c": self.peak_resistor_temperature_c,
            "time_to_stop_s": self.time_to_stop_s,
            "points": len(self.time_s),
            "events": self.events,
        }


def simulate_passive_balancing(
    cells: Sequence[PackCellModel],
    limits: ProtectionLimits,
    *,
    duration_s: float,
    step_s: float,
    permitted: bool = True,
    ambient_temperature_c: float | None = None,
) -> BalancingRunResult:
    """在冻结 ECM 上执行被动均衡长时间仿真。

    均衡电流只作用于被选中的单体，主回路电流为零（静置均衡）。SOC 按真实
    库仑积分更新，不使用预设曲线。
    """
    if not cells:
        raise BalancingError("至少需要一节电芯")
    if duration_s <= 0.0 or step_s <= 0.0:
        raise BalancingError("时长与步长必须为正")
    balancer = PassiveBalancer(limits)
    cell_ids = [cell.cell_id for cell in cells]

    time_list: list[float] = []
    pack_list: list[float] = []
    max_list: list[float] = []
    min_list: list[float] = []
    delta_list: list[float] = []
    soc_history: dict[str, list[float]] = {cell_id: [] for cell_id in cell_ids}
    voltage_history: dict[str, list[float]] = {cell_id: [] for cell_id in cell_ids}
    current_history: dict[str, list[float]] = {cell_id: [] for cell_id in cell_ids}
    events: list[dict[str, Any]] = []

    energy_j = 0.0
    peak_power = 0.0
    peak_temperature = limits.balance_ambient_temperature_c if ambient_temperature_c is None else float(ambient_temperature_c)
    time_to_stop: float | None = None
    initial_delta: float | None = None

    steps = int(round(duration_s / step_s))
    for index in range(steps + 1):
        now = index * step_s
        voltages = [cell.terminal_voltage_v(0.0) for cell in cells]
        delta = max(voltages) - min(voltages)
        if initial_delta is None:
            initial_delta = delta
        channels = balancer.plan(
            cell_ids,
            voltages,
            permitted=permitted,
            ambient_temperature_c=ambient_temperature_c,
        )
        if permitted and delta <= limits.balance_stop_delta_v and time_to_stop is None:
            time_to_stop = now
            events.append({"time_s": now, "event": "balancing_complete", "delta_v": delta})

        time_list.append(now)
        pack_list.append(float(sum(voltages)))
        max_list.append(float(max(voltages)))
        min_list.append(float(min(voltages)))
        delta_list.append(delta)
        for cell, channel in zip(cells, channels):
            soc_history[cell.cell_id].append(cell.state.soc)
            voltage_history[cell.cell_id].append(channel.cell_voltage_v)
            current_history[cell.cell_id].append(channel.current_a)
            if channel.enabled:
                energy_j += channel.power_w * step_s
                peak_power = max(peak_power, channel.power_w)
                peak_temperature = max(
                    peak_temperature, balancer.resistor_temperature_c(channel.power_w, ambient_temperature_c)
                )

        if index == steps:
            break
        for cell, channel in zip(cells, channels):
            cell.step(channel.current_a, step_s)

    final_delta = delta_list[-1]
    assert initial_delta is not None
    reduction = 0.0 if initial_delta <= 0.0 else (initial_delta - final_delta) / initial_delta
    return BalancingRunResult(
        time_s=time_list,
        pack_voltage_v=pack_list,
        max_cell_voltage_v=max_list,
        min_cell_voltage_v=min_list,
        delta_cell_voltage_v=delta_list,
        cell_soc=soc_history,
        cell_voltage=voltage_history,
        balance_current=current_history,
        energy_dissipated_wh=energy_j / 3600.0,
        peak_resistor_power_w=peak_power,
        peak_resistor_temperature_c=peak_temperature,
        initial_delta_v=initial_delta,
        final_delta_v=final_delta,
        delta_reduction_fraction=reduction,
        time_to_stop_s=time_to_stop,
        events=events,
    )

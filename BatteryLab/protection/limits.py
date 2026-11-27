"""第五阶段保护阈值：加载、可追溯性校验与一致性检查。

阈值不是凭感觉设定：每个电压阈值都要落在第四阶段采集有效域内，并与第三阶段
冻结电芯模型的端电压参考区间保持正确关系。任何越界或关系倒置都会直接抛错，
不允许静默修正。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from battery_models.parameters import load_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"


class ProtectionConfigError(ValueError):
    """保护配置非法。"""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtectionConfigError(f"{name} 必须是数值，实际为 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ProtectionConfigError(f"{name} 必须是有限数值，实际为 {number!r}")
    return number


def _positive(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number <= 0.0:
        raise ProtectionConfigError(f"{name} 必须为正数，实际为 {number!r}")
    return number


def _section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    section = config.get(key)
    if not isinstance(section, Mapping):
        raise ProtectionConfigError(f"缺少配置段: {key}")
    return section


@dataclass(frozen=True)
class ProtectionLimits:
    """所有保护阈值、时序与均衡参数。单位已在字段名中声明。"""

    capacity_ah: float

    model_terminal_reference_min_v: float
    model_terminal_reference_max_v: float
    afe_measurement_min_v: float
    afe_measurement_max_v: float
    stage3_observed_cell_min_v: float
    stage3_observed_cell_max_v: float

    cell_overvoltage_trip_v: float
    cell_overvoltage_release_v: float
    cell_undervoltage_trip_v: float
    cell_undervoltage_release_v: float

    charge_overcurrent_trip_a: float
    charge_overcurrent_release_a: float
    discharge_overcurrent_trip_a: float
    discharge_overcurrent_release_a: float
    short_circuit_trip_a: float
    short_circuit_release_a: float

    over_temperature_trip_c: float
    over_temperature_release_c: float
    charge_temperature_min_c: float
    charge_temperature_max_c: float
    discharge_temperature_min_c: float
    discharge_temperature_max_c: float
    temperature_release_margin_c: float

    overvoltage_delay_s: float
    undervoltage_delay_s: float
    charge_overcurrent_delay_s: float
    discharge_overcurrent_delay_s: float
    short_circuit_delay_s: float
    over_temperature_delay_s: float
    under_temperature_delay_s: float
    comparator_propagation_delay_s: float
    measurement_max_age_s: float

    all_clear_hold_s: float
    automatic_restart: bool

    rds_on_target_ohm: float
    body_diode_saturation_current_a: float
    gate_drive_voltage_v: float
    gate_resistance_ohm: float
    gate_pulldown_ohm: float
    gate_charge_nc: float
    switching_frequency_hz: float
    driver_supply_v: float
    drain_access_resistance_ohm: float
    source_access_resistance_ohm: float
    mosfet_thermal_resistance_c_per_w: float

    balance_resistor_ohm: float
    balance_mosfet_rds_on_ohm: float
    balance_start_cell_voltage_v: float
    balance_start_delta_v: float
    balance_stop_delta_v: float
    balance_max_simultaneous_cells: int
    balance_resistor_power_rating_w: float
    balance_resistor_thermal_resistance_c_per_w: float
    balance_ambient_temperature_c: float
    balance_step_s: float

    parameter_source: str
    hardware_validation_available: bool

    def validate(self) -> "ProtectionLimits":
        """检查阈值与模型/采集有效域的一致性。"""
        # 电压：必须落在采集有效域内，且不越过模型参考上限/下限。
        if not self.model_terminal_reference_min_v < self.model_terminal_reference_max_v:
            raise ProtectionConfigError("模型参考电压下限必须小于上限")
        if not self.afe_measurement_min_v < self.afe_measurement_max_v:
            raise ProtectionConfigError("AFE 采集范围下限必须小于上限")
        if self.cell_overvoltage_trip_v > self.afe_measurement_max_v:
            raise ProtectionConfigError("过压阈值不能超出采集上限，否则永远测不到")
        if self.cell_overvoltage_trip_v < self.model_terminal_reference_max_v:
            raise ProtectionConfigError("过压阈值不能低于模型参考上限")
        if not self.cell_overvoltage_release_v < self.cell_overvoltage_trip_v:
            raise ProtectionConfigError("过压释放阈值必须低于触发阈值")
        if self.cell_undervoltage_trip_v < self.afe_measurement_min_v:
            raise ProtectionConfigError("欠压阈值不能低于采集下限")
        if self.cell_undervoltage_trip_v > self.model_terminal_reference_min_v:
            raise ProtectionConfigError("欠压阈值不能高于模型参考下限")
        if not self.cell_undervoltage_release_v > self.cell_undervoltage_trip_v:
            raise ProtectionConfigError("欠压释放阈值必须高于触发阈值")
        if self.cell_undervoltage_release_v > self.model_terminal_reference_min_v:
            raise ProtectionConfigError("欠压释放阈值不能高于模型参考下限")

        # 电流：触发必须大于释放，短路必须最严。
        if not 0.0 < self.charge_overcurrent_release_a < self.charge_overcurrent_trip_a:
            raise ProtectionConfigError("充电过流释放必须小于触发且为正")
        if not 0.0 < self.discharge_overcurrent_release_a < self.discharge_overcurrent_trip_a:
            raise ProtectionConfigError("放电过流释放必须小于触发且为正")
        if not self.short_circuit_trip_a > self.discharge_overcurrent_trip_a:
            raise ProtectionConfigError("短路阈值必须高于放电过流阈值")

        # 温度：充电与放电区间、过温均需一致。
        if not self.charge_temperature_min_c < self.charge_temperature_max_c:
            raise ProtectionConfigError("充电温度区间非法")
        if not self.discharge_temperature_min_c < self.discharge_temperature_max_c:
            raise ProtectionConfigError("放电温度区间非法")
        if not self.over_temperature_release_c < self.over_temperature_trip_c:
            raise ProtectionConfigError("过温释放必须低于触发")
        if not self.over_temperature_trip_c > self.charge_temperature_max_c:
            raise ProtectionConfigError("过温阈值必须高于充电上限温度")
        if not self.over_temperature_trip_c > self.discharge_temperature_max_c:
            raise ProtectionConfigError("过温阈值必须高于放电上限温度")
        if self.temperature_release_margin_c <= 0.0:
            raise ProtectionConfigError("温度释放回差必须为正")

        # 时序：全部必须为正。
        for name in (
            "overvoltage_delay_s",
            "undervoltage_delay_s",
            "charge_overcurrent_delay_s",
            "discharge_overcurrent_delay_s",
            "short_circuit_delay_s",
            "over_temperature_delay_s",
            "under_temperature_delay_s",
            "comparator_propagation_delay_s",
            "measurement_max_age_s",
            "all_clear_hold_s",
        ):
            _positive(getattr(self, name), name)

        # 均衡：启动条件与回差必须自洽。
        if not 0.0 < self.balance_stop_delta_v < self.balance_start_delta_v:
            raise ProtectionConfigError("均衡停止回差必须小于启动回差")
        if self.balance_start_cell_voltage_v >= self.cell_overvoltage_trip_v:
            raise ProtectionConfigError("均衡启动电压必须低于过压触发")
        if self.balance_max_simultaneous_cells < 1:
            raise ProtectionConfigError("均衡同时开启节数至少为 1")
        _positive(self.balance_resistor_ohm, "balance_resistor_ohm")
        _positive(self.balance_resistor_power_rating_w, "balance_resistor_power_rating_w")
        _positive(self.balance_resistor_thermal_resistance_c_per_w, "balance_resistor_thermal_resistance_c_per_w")

        # MOSFET：栅压、电荷与频率必须为正。
        for name in (
            "rds_on_target_ohm",
            "body_diode_saturation_current_a",
            "gate_drive_voltage_v",
            "gate_resistance_ohm",
            "gate_pulldown_ohm",
            "gate_charge_nc",
            "switching_frequency_hz",
            "driver_supply_v",
            "mosfet_thermal_resistance_c_per_w",
        ):
            _positive(getattr(self, name), name)
        if self.automatic_restart:
            raise ProtectionConfigError("本阶段禁止自动重启")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    def threshold_provenance(self) -> dict[str, Any]:
        """返回每个电压阈值的可追溯依据。"""
        return {
            "cell_overvoltage_trip_v": {
                "value": self.cell_overvoltage_trip_v,
                "lower_bound": self.model_terminal_reference_max_v,
                "upper_bound": self.afe_measurement_max_v,
                "basis": "等于第四阶段 AFE 采集上限，且高于第三阶段模型参考上限",
            },
            "cell_overvoltage_release_v": {
                "value": self.cell_overvoltage_release_v,
                "hysteresis_v": self.cell_overvoltage_trip_v - self.cell_overvoltage_release_v,
                "basis": "100 mV 回差，保证噪声下不抖动",
            },
            "cell_undervoltage_trip_v": {
                "value": self.cell_undervoltage_trip_v,
                "lower_bound": self.afe_measurement_min_v,
                "upper_bound": self.model_terminal_reference_min_v,
                "basis": "高于采集下限 2.5 V，低于模型参考下限 3.0 V",
            },
            "cell_undervoltage_release_v": {
                "value": self.cell_undervoltage_release_v,
                "hysteresis_v": self.cell_undervoltage_release_v - self.cell_undervoltage_trip_v,
                "basis": "200 mV 回差，恢复后不立即再次触发",
            },
        }


def load_protection_config(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else CONFIG_DIR / "protection_config.yaml"
    payload = load_yaml(target)
    if not isinstance(payload, Mapping):
        raise ProtectionConfigError("protection_config.yaml 顶层必须是映射")
    return dict(payload)


def build_limits(config: Mapping[str, Any] | None = None) -> ProtectionLimits:
    """从配置构造并校验保护阈值。"""
    raw = dict(config) if config is not None else load_protection_config()
    cell = _section(raw, "cell_reference")
    limits = _section(raw, "limits")
    timing = _section(raw, "timing")
    recovery = _section(raw, "recovery")
    switch = _section(raw, "mosfet_switch")
    balance = _section(raw, "balancing")

    result = ProtectionLimits(
        capacity_ah=_positive(cell["capacity_ah"], "cell_reference.capacity_ah"),
        model_terminal_reference_min_v=_positive(
            cell["model_terminal_reference_min_v"], "cell_reference.model_terminal_reference_min_v"
        ),
        model_terminal_reference_max_v=_positive(
            cell["model_terminal_reference_max_v"], "cell_reference.model_terminal_reference_max_v"
        ),
        afe_measurement_min_v=_positive(cell["afe_measurement_min_v"], "cell_reference.afe_measurement_min_v"),
        afe_measurement_max_v=_positive(cell["afe_measurement_max_v"], "cell_reference.afe_measurement_max_v"),
        stage3_observed_cell_min_v=_finite(
            cell["stage3_observed_cell_min_v"], "cell_reference.stage3_observed_cell_min_v"
        ),
        stage3_observed_cell_max_v=_finite(
            cell["stage3_observed_cell_max_v"], "cell_reference.stage3_observed_cell_max_v"
        ),
        cell_overvoltage_trip_v=_positive(limits["cell_overvoltage_trip_v"], "limits.cell_overvoltage_trip_v"),
        cell_overvoltage_release_v=_positive(
            limits["cell_overvoltage_release_v"], "limits.cell_overvoltage_release_v"
        ),
        cell_undervoltage_trip_v=_positive(limits["cell_undervoltage_trip_v"], "limits.cell_undervoltage_trip_v"),
        cell_undervoltage_release_v=_positive(
            limits["cell_undervoltage_release_v"], "limits.cell_undervoltage_release_v"
        ),
        charge_overcurrent_trip_a=_positive(limits["charge_overcurrent_trip_a"], "limits.charge_overcurrent_trip_a"),
        charge_overcurrent_release_a=_positive(
            limits["charge_overcurrent_release_a"], "limits.charge_overcurrent_release_a"
        ),
        discharge_overcurrent_trip_a=_positive(
            limits["discharge_overcurrent_trip_a"], "limits.discharge_overcurrent_trip_a"
        ),
        discharge_overcurrent_release_a=_positive(
            limits["discharge_overcurrent_release_a"], "limits.discharge_overcurrent_release_a"
        ),
        short_circuit_trip_a=_positive(limits["short_circuit_trip_a"], "limits.short_circuit_trip_a"),
        short_circuit_release_a=_positive(limits["short_circuit_release_a"], "limits.short_circuit_release_a"),
        over_temperature_trip_c=_finite(limits["over_temperature_trip_c"], "limits.over_temperature_trip_c"),
        over_temperature_release_c=_finite(limits["over_temperature_release_c"], "limits.over_temperature_release_c"),
        charge_temperature_min_c=_finite(limits["charge_temperature_min_c"], "limits.charge_temperature_min_c"),
        charge_temperature_max_c=_finite(limits["charge_temperature_max_c"], "limits.charge_temperature_max_c"),
        discharge_temperature_min_c=_finite(
            limits["discharge_temperature_min_c"], "limits.discharge_temperature_min_c"
        ),
        discharge_temperature_max_c=_finite(
            limits["discharge_temperature_max_c"], "limits.discharge_temperature_max_c"
        ),
        temperature_release_margin_c=_positive(
            limits["temperature_release_margin_c"], "limits.temperature_release_margin_c"
        ),
        overvoltage_delay_s=_positive(timing["overvoltage_delay_s"], "timing.overvoltage_delay_s"),
        undervoltage_delay_s=_positive(timing["undervoltage_delay_s"], "timing.undervoltage_delay_s"),
        charge_overcurrent_delay_s=_positive(
            timing["charge_overcurrent_delay_s"], "timing.charge_overcurrent_delay_s"
        ),
        discharge_overcurrent_delay_s=_positive(
            timing["discharge_overcurrent_delay_s"], "timing.discharge_overcurrent_delay_s"
        ),
        short_circuit_delay_s=_positive(timing["short_circuit_delay_s"], "timing.short_circuit_delay_s"),
        over_temperature_delay_s=_positive(timing["over_temperature_delay_s"], "timing.over_temperature_delay_s"),
        under_temperature_delay_s=_positive(timing["under_temperature_delay_s"], "timing.under_temperature_delay_s"),
        comparator_propagation_delay_s=_positive(
            timing["comparator_propagation_delay_s"], "timing.comparator_propagation_delay_s"
        ),
        measurement_max_age_s=_positive(timing["measurement_max_age_s"], "timing.measurement_max_age_s"),
        all_clear_hold_s=_positive(recovery["all_clear_hold_s"], "recovery.all_clear_hold_s"),
        automatic_restart=bool(recovery["automatic_restart"]),
        rds_on_target_ohm=_positive(switch["rds_on_target_ohm"], "mosfet_switch.rds_on_target_ohm"),
        body_diode_saturation_current_a=_positive(
            switch["body_diode_saturation_current_a"], "mosfet_switch.body_diode_saturation_current_a"
        ),
        gate_drive_voltage_v=_positive(switch["gate_drive_voltage_v"], "mosfet_switch.gate_drive_voltage_v"),
        gate_resistance_ohm=_positive(switch["gate_resistance_ohm"], "mosfet_switch.gate_resistance_ohm"),
        gate_pulldown_ohm=_positive(switch["gate_pulldown_ohm"], "mosfet_switch.gate_pulldown_ohm"),
        gate_charge_nc=_positive(switch["gate_charge_nc"], "mosfet_switch.gate_charge_nc"),
        switching_frequency_hz=_positive(
            switch["switching_frequency_hz"], "mosfet_switch.switching_frequency_hz"
        ),
        driver_supply_v=_positive(switch["driver_supply_v"], "mosfet_switch.driver_supply_v"),
        drain_access_resistance_ohm=_positive(
            switch["drain_access_resistance_ohm"], "mosfet_switch.drain_access_resistance_ohm"
        ),
        source_access_resistance_ohm=_positive(
            switch["source_access_resistance_ohm"], "mosfet_switch.source_access_resistance_ohm"
        ),
        mosfet_thermal_resistance_c_per_w=_positive(
            switch["thermal_resistance_c_per_w"], "mosfet_switch.thermal_resistance_c_per_w"
        ),
        balance_resistor_ohm=_positive(balance["resistor_ohm"], "balancing.resistor_ohm"),
        balance_mosfet_rds_on_ohm=_positive(balance["mosfet_rds_on_ohm"], "balancing.mosfet_rds_on_ohm"),
        balance_start_cell_voltage_v=_positive(
            balance["start_cell_voltage_v"], "balancing.start_cell_voltage_v"
        ),
        balance_start_delta_v=_positive(balance["start_delta_v"], "balancing.start_delta_v"),
        balance_stop_delta_v=_positive(balance["stop_delta_v"], "balancing.stop_delta_v"),
        balance_max_simultaneous_cells=int(balance["max_simultaneous_cells"]),
        balance_resistor_power_rating_w=_positive(
            balance["resistor_power_rating_w"], "balancing.resistor_power_rating_w"
        ),
        balance_resistor_thermal_resistance_c_per_w=_positive(
            balance["resistor_thermal_resistance_c_per_w"], "balancing.resistor_thermal_resistance_c_per_w"
        ),
        balance_ambient_temperature_c=_finite(
            balance["ambient_temperature_c"], "balancing.ambient_temperature_c"
        ),
        balance_step_s=_positive(balance["balancing_step_s"], "balancing.balancing_step_s"),
        parameter_source=str(raw.get("parameter_source", "unknown")),
        hardware_validation_available=bool(
            _section(raw, "metadata").get("hardware_validation_available", False)
        ),
    )
    return result.validate()


def load_limits(path: str | Path | None = None) -> ProtectionLimits:
    return build_limits(load_protection_config(path))


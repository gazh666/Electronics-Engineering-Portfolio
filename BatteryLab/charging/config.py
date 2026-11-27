"""第六阶段充电系统配置：加载与严格校验。

配置值只是教学设计假设。校验会检查功率级可达性，并与第五阶段真实保护限值协调，
任何冲突直接抛错，不允许静默修正。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from battery_models.parameters import load_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"


class ChargerConfigError(ValueError):
    """充电配置非法。"""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ChargerConfigError(f"{name} 必须是数值，实际为 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ChargerConfigError(f"{name} 必须是有限数值，实际为 {number!r}")
    return number


def _positive(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number <= 0.0:
        raise ChargerConfigError(f"{name} 必须为正数，实际为 {number!r}")
    return number


def _non_negative(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number < 0.0:
        raise ChargerConfigError(f"{name} 不能为负，实际为 {number!r}")
    return number


def _section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    section = config.get(key)
    if not isinstance(section, Mapping):
        raise ChargerConfigError(f"缺少配置段: {key}")
    return section


@dataclass(frozen=True)
class PowerStageConfig:
    input_voltage_v: float
    switching_frequency_hz: float
    inductance_h: float
    capacitance_f: float
    inductor_dcr_ohm: float
    capacitor_esr_ohm: float
    diode_forward_voltage_estimate_v: float
    mosfet_rds_on_target_ohm: float
    path_resistance_ohm: float

    def validate(self, voltage_target_v: float, duty_max: float) -> "PowerStageConfig":
        if self.input_voltage_v <= voltage_target_v:
            raise ChargerConfigError("输入电压必须高于恒压目标，否则 Buck 无法升压")
        if voltage_target_v / self.input_voltage_v > duty_max:
            raise ChargerConfigError("恒压目标所需占空比超过 duty_max")
        for name in (
            "switching_frequency_hz",
            "inductance_h",
            "capacitance_f",
            "mosfet_rds_on_target_ohm",
        ):
            _positive(getattr(self, name), name)
        _non_negative(self.inductor_dcr_ohm, "inductor_dcr_ohm")
        _non_negative(self.capacitor_esr_ohm, "capacitor_esr_ohm")
        _non_negative(self.path_resistance_ohm, "path_resistance_ohm")
        _non_negative(self.diode_forward_voltage_estimate_v, "diode_forward_voltage_estimate_v")
        return self

    def to_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class BatterySpec:
    series_cells: int
    parallel_cells: int
    reference_capacity_ah: float
    identified_model_id: str
    identified_soc_min: float
    identified_soc_max: float

    def validate(self) -> "BatterySpec":
        if self.series_cells < 1:
            raise ChargerConfigError("串联节数至少为 1")
        if self.parallel_cells != 1:
            raise ChargerConfigError("本阶段只支持 1P")
        _positive(self.reference_capacity_ah, "reference_capacity_ah")
        if not self.identified_model_id:
            raise ChargerConfigError("必须提供第三阶段冻结辨识模型 ID")
        if not 0.0 <= self.identified_soc_min < self.identified_soc_max <= 1.0:
            raise ChargerConfigError("辨识 SOC 区间非法")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class ChargingSpec:
    constant_current_a: float
    constant_voltage_v: float
    termination_current_a: float
    termination_hold_time_s: float
    maximum_charge_time_s: float
    soft_start_time_s: float
    precharge_enabled: bool
    automatic_restart_enabled: bool

    def validate(self) -> "ChargingSpec":
        _positive(self.constant_current_a, "constant_current_a")
        _positive(self.constant_voltage_v, "constant_voltage_v")
        _positive(self.termination_current_a, "termination_current_a")
        if not self.termination_current_a < self.constant_current_a:
            raise ChargerConfigError("终止电流必须小于恒流值")
        _positive(self.termination_hold_time_s, "termination_hold_time_s")
        _positive(self.maximum_charge_time_s, "maximum_charge_time_s")
        if self.maximum_charge_time_s <= self.termination_hold_time_s:
            raise ChargerConfigError("最大充电时间必须大于终止保持时间")
        _non_negative(self.soft_start_time_s, "soft_start_time_s")
        if self.precharge_enabled:
            raise ChargerConfigError("本阶段未实现预充电，配置必须为 false")
        if self.automatic_restart_enabled:
            raise ChargerConfigError("本阶段禁止自动重启")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class ControllerLimitConfig:
    duty_min: float
    duty_max: float
    control_period_s: float

    def validate(self) -> "ControllerLimitConfig":
        if not 0.0 <= self.duty_min < self.duty_max < 1.0:
            raise ChargerConfigError("占空比范围必须满足 0 <= min < max < 1")
        _positive(self.control_period_s, "control_period_s")
        return self

    def to_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class ChargerConfig:
    version: str
    parameter_source: str
    battery: BatterySpec
    power_stage: PowerStageConfig
    charging: ChargingSpec
    controller: ControllerLimitConfig
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def output_voltage_target_v(self) -> float:
        return self.charging.constant_voltage_v

    def validate(self) -> "ChargerConfig":
        self.battery.validate()
        self.charging.validate()
        self.controller.validate()
        self.power_stage.validate(self.output_voltage_target_v, self.controller.duty_max)
        return self

    def validate_against_protection(self) -> dict[str, Any]:
        """与第五阶段真实保护限值协调；不允许通过降低保护来满足充电目标。"""
        from protection.limits import load_limits

        limits = load_limits()
        per_cell = self.output_voltage_target_v / self.battery.series_cells
        if per_cell > limits.cell_overvoltage_release_v:
            raise ChargerConfigError(
                f"恒压目标折算单体 {per_cell:.4f} V 高于过压释放 {limits.cell_overvoltage_release_v} V"
            )
        if per_cell < limits.cell_undervoltage_release_v:
            raise ChargerConfigError(
                f"恒压目标折算单体 {per_cell:.4f} V 低于欠压释放 {limits.cell_undervoltage_release_v} V"
            )
        if limits.charge_overcurrent_trip_a <= self.charging.constant_current_a:
            raise ChargerConfigError("第五阶段充电过流阈值必须高于本阶段恒流值")
        if limits.automatic_restart:
            raise ChargerConfigError("第五阶段禁止自动重启，第六阶段也必须禁止")
        return {
            "per_cell_cv_v": per_cell,
            "cell_overvoltage_trip_v": limits.cell_overvoltage_trip_v,
            "cell_overvoltage_release_v": limits.cell_overvoltage_release_v,
            "charge_overcurrent_trip_a": limits.charge_overcurrent_trip_a,
            "charge_temperature_min_c": limits.charge_temperature_min_c,
            "charge_temperature_max_c": limits.charge_temperature_max_c,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "parameter_source": self.parameter_source,
            "battery": self.battery.to_dict(),
            "power_stage": self.power_stage.to_dict(),
            "charging": self.charging.to_dict(),
            "controller": self.controller.to_dict(),
            "metadata": dict(self.metadata),
        }


def load_charger_config(path: str | Path | None = None) -> ChargerConfig:
    target = Path(path) if path is not None else CONFIG_DIR / "charger_config.yaml"
    raw = load_yaml(target)
    battery = _section(raw, "battery")
    power = _section(raw, "power_stage")
    charging = _section(raw, "charging")
    controller = _section(raw, "controller")
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ChargerConfigError("metadata 必须是映射")
    config = ChargerConfig(
        version=str(raw.get("version", "1.0")),
        parameter_source=str(raw.get("parameter_source", "educational_assumption")),
        battery=BatterySpec(
            series_cells=int(battery["series_cells"]),
            parallel_cells=int(battery["parallel_cells"]),
            reference_capacity_ah=_positive(battery["reference_capacity_ah"], "battery.reference_capacity_ah"),
            identified_model_id=str(battery["identified_model_id"]),
            identified_soc_min=_finite(battery["identified_soc_min"], "battery.identified_soc_min"),
            identified_soc_max=_finite(battery["identified_soc_max"], "battery.identified_soc_max"),
        ),
        power_stage=PowerStageConfig(
            input_voltage_v=_positive(power["input_voltage_v"], "power_stage.input_voltage_v"),
            switching_frequency_hz=_positive(
                power["switching_frequency_hz"], "power_stage.switching_frequency_hz"
            ),
            inductance_h=_positive(power["inductance_h"], "power_stage.inductance_h"),
            capacitance_f=_positive(power["capacitance_f"], "power_stage.capacitance_f"),
            inductor_dcr_ohm=_non_negative(power["inductor_dcr_ohm"], "power_stage.inductor_dcr_ohm"),
            capacitor_esr_ohm=_non_negative(power["capacitor_esr_ohm"], "power_stage.capacitor_esr_ohm"),
            diode_forward_voltage_estimate_v=_non_negative(
                power["diode_forward_voltage_estimate_v"], "power_stage.diode_forward_voltage_estimate_v"
            ),
            mosfet_rds_on_target_ohm=_positive(
                power["mosfet_rds_on_target_ohm"], "power_stage.mosfet_rds_on_target_ohm"
            ),
            path_resistance_ohm=_non_negative(power["path_resistance_ohm"], "power_stage.path_resistance_ohm"),
        ),
        charging=ChargingSpec(
            constant_current_a=_positive(charging["constant_current_a"], "charging.constant_current_a"),
            constant_voltage_v=_positive(charging["constant_voltage_v"], "charging.constant_voltage_v"),
            termination_current_a=_positive(
                charging["termination_current_a"], "charging.termination_current_a"
            ),
            termination_hold_time_s=_positive(
                charging["termination_hold_time_s"], "charging.termination_hold_time_s"
            ),
            maximum_charge_time_s=_positive(
                charging["maximum_charge_time_s"], "charging.maximum_charge_time_s"
            ),
            soft_start_time_s=_non_negative(charging["soft_start_time_s"], "charging.soft_start_time_s"),
            precharge_enabled=bool(charging["precharge_enabled"]),
            automatic_restart_enabled=bool(charging["automatic_restart_enabled"]),
        ),
        controller=ControllerLimitConfig(
            duty_min=_non_negative(controller["duty_min"], "controller.duty_min"),
            duty_max=_positive(controller["duty_max"], "controller.duty_max"),
            control_period_s=_positive(controller["control_period_s"], "controller.control_period_s"),
        ),
        metadata=dict(metadata),
    )
    return config.validate()


@dataclass(frozen=True)
class LoopGains:
    kp: float
    ki: float
    kaw: float

    def validate(self, name: str) -> "LoopGains":
        _non_negative(self.kp, f"{name}.kp")
        _positive(self.ki, f"{name}.ki")
        _non_negative(self.kaw, f"{name}.kaw")
        return self

    def to_dict(self) -> dict[str, float]:
        return {"kp": self.kp, "ki": self.ki, "kaw": self.kaw}


@dataclass(frozen=True)
class ControllerConfig:
    source_type: str
    voltage_loop: LoopGains
    current_loop: LoopGains
    current_min_a: float
    current_max_a: float
    duty_min: float
    duty_max: float
    control_period_s: float

    def validate(self) -> "ControllerConfig":
        self.voltage_loop.validate("voltage_loop")
        self.current_loop.validate("current_loop")
        _non_negative(self.current_min_a, "current_min_a")
        _positive(self.current_max_a, "current_max_a")
        if self.current_max_a <= self.current_min_a:
            raise ChargerConfigError("电流上限必须大于下限")
        if not 0.0 <= self.duty_min < self.duty_max < 1.0:
            raise ChargerConfigError("占空比范围非法")
        _positive(self.control_period_s, "control_period_s")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "voltage_loop": self.voltage_loop.to_dict(),
            "current_loop": self.current_loop.to_dict(),
            "limits": {
                "current_min_a": self.current_min_a,
                "current_max_a": self.current_max_a,
                "duty_min": self.duty_min,
                "duty_max": self.duty_max,
            },
            "sampling": {"control_period_s": self.control_period_s},
        }


def load_controller_config(path: str | Path | None = None) -> ControllerConfig:
    target = Path(path) if path is not None else CONFIG_DIR / "charge_controller.yaml"
    raw = load_yaml(target)
    voltage = _section(raw, "voltage_loop")
    current = _section(raw, "current_loop")
    limits = _section(raw, "limits")
    sampling = _section(raw, "sampling")
    config = ControllerConfig(
        source_type=str(raw.get("source_type", "educational_initial_guess")),
        voltage_loop=LoopGains(
            kp=_non_negative(voltage["kp_a_per_v"], "voltage_loop.kp"),
            ki=_positive(voltage["ki_a_per_vs"], "voltage_loop.ki"),
            kaw=_non_negative(voltage["anti_windup_per_s"], "voltage_loop.kaw"),
        ),
        current_loop=LoopGains(
            kp=_non_negative(current["kp_duty_per_a"], "current_loop.kp"),
            ki=_positive(current["ki_duty_per_as"], "current_loop.ki"),
            kaw=_non_negative(current["anti_windup_per_s"], "current_loop.kaw"),
        ),
        current_min_a=_non_negative(limits["current_min_a"], "limits.current_min_a"),
        current_max_a=_positive(limits["current_max_a"], "limits.current_max_a"),
        duty_min=_non_negative(limits["duty_min"], "limits.duty_min"),
        duty_max=_positive(limits["duty_max"], "limits.duty_max"),
        control_period_s=_positive(sampling["control_period_s"], "sampling.control_period_s"),
    )
    return config.validate()


def load_tuning_grid(path: str | Path | None = None) -> dict[str, list[float]]:
    target = Path(path) if path is not None else CONFIG_DIR / "charge_controller.yaml"
    raw = load_yaml(target)
    grid = _section(raw, "tuning_grid")
    return {
        "current_kp": [float(v) for v in grid["current_kp"]],
        "current_ki": [float(v) for v in grid["current_ki"]],
        "voltage_kp": [float(v) for v in grid["voltage_kp"]],
        "voltage_ki": [float(v) for v in grid["voltage_ki"]],
    }


def load_engineering_targets(path: str | Path | None = None) -> dict[str, float]:
    target = Path(path) if path is not None else CONFIG_DIR / "charge_controller.yaml"
    raw = load_yaml(target)
    return {str(key): float(value) for key, value in _section(raw, "engineering_targets").items()}


@dataclass(frozen=True)
class ChargingCase:
    id: str
    name: str
    method: str
    description: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "method": self.method,
            "description": self.description,
            "parameters": dict(self.parameters),
        }


def load_charging_cases(path: str | Path | None = None) -> list[ChargingCase]:
    from charging.models import validate_method

    target = Path(path) if path is not None else CONFIG_DIR / "charging_cases.yaml"
    raw = load_yaml(target)
    rows = raw.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ChargerConfigError("charging_cases.yaml 必须包含非空 cases 列表")
    cases = []
    for row in rows:
        params = row.get("parameters", {})
        if not isinstance(params, Mapping):
            raise ChargerConfigError(f"{row.get('id')}: parameters 必须是映射")
        cases.append(
            ChargingCase(
                id=str(row["id"]),
                name=str(row["name"]),
                method=validate_method(str(row["method"])),
                description=str(row.get("description", "")),
                parameters=dict(params),
            )
        )
    identifiers = [case.id for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ChargerConfigError("工况编号必须唯一")
    return cases


def load_validation_config(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else CONFIG_DIR / "stage6_validation.yaml"
    raw = load_yaml(target)
    budget = _section(raw, "simulation_budget")
    limits = _section(raw, "preregistered_limits")
    return {
        "budget": {
            "maximum_spice_solves": int(budget["maximum_spice_solves"]),
            "maximum_case_duration_seconds": float(budget["maximum_case_duration_seconds"]),
            "maximum_total_runtime_minutes": float(budget["maximum_total_runtime_minutes"]),
            "maximum_average_model_runs": int(budget["maximum_average_model_runs"]),
            "profiles": dict(raw.get("profiles", {})),
        },
        "limits": {str(key): float(value) for key, value in limits.items()},
    }

"""第四阶段非理想 Buck 统一配置（SI 单位）。

本模块只做参数定义、校验、YAML 读取与快照导出，不构建电路、不执行仿真。

所有数值均来自 ``configs/nonideal_buck_config.yaml`` 或
``configs/device_models.yaml``，缺失字段直接报错，不使用隐式默认值兜底。

模型来源标注 ``educational_assumption``：Level 1 MOSFET 与低储存电荷二极管
均为教学用简化模型，不是经过验证的商业器件 SPICE 模型。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .buck_config import SteadyStateConfig, TransientConfig
from .pwm import PWMParameters
from .validators import (
    finite_number,
    nonnegative_number,
    positive_integer,
    positive_number,
    temperature_celsius,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NONIDEAL_CONFIG_PATH = PROJECT_ROOT / "configs" / "nonideal_buck_config.yaml"
DEFAULT_DEVICE_MODELS_PATH = PROJECT_ROOT / "configs" / "device_models.yaml"
DEFAULT_VALIDATION_PATH = PROJECT_ROOT / "configs" / "nonideal_validation.yaml"

#: 当前支持的 MOSFET 模型级别（只实现 Level 1 教学模型）。
SUPPORTED_MOSFET_LEVELS = (1,)

#: 允许的驱动类型标识（本阶段只实现理想浮动源）。
SUPPORTED_DRIVER_TYPES = ("ideal_floating_source",)


@dataclass(frozen=True)
class MosfetModelConfig:
    """Level 1 增强型 N 沟道 MOSFET 教学模型参数。"""

    model_name: str = "NMOS_EDU"
    model_type: str = "NMOS"
    level: int = 1
    threshold_voltage_v: float = 3.0
    kp_a_per_v2: float = 0.01
    channel_length_m: float = 1e-6
    channel_width_m: float = 1e-3
    channel_length_modulation_per_v: float = 0.001
    drain_resistance_ohm: float = 0.005
    source_resistance_ohm: float = 0.002
    external_cgs_f: float = 1e-9
    external_cgd_f: float = 2e-10
    external_cds_f: float = 3e-10
    model_source: str = "educational_assumption"
    model_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("model_name", "model_type", "model_source", "model_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"mosfet.{name} must be a non-empty string")
        if self.model_type.strip().upper() != "NMOS":
            raise ValueError("mosfet.model_type must be NMOS for this high-side topology")
        level = positive_integer(self.level, "mosfet.level", minimum=1)
        if level not in SUPPORTED_MOSFET_LEVELS:
            raise ValueError(f"mosfet.level {level} is not supported; use {SUPPORTED_MOSFET_LEVELS}")

        threshold = positive_number(self.threshold_voltage_v, "mosfet.threshold_voltage_v")
        positive_number(self.kp_a_per_v2, "mosfet.kp_a_per_v2")
        positive_number(self.channel_length_m, "mosfet.channel_length_m")
        positive_number(self.channel_width_m, "mosfet.channel_width_m")
        nonnegative_number(
            self.channel_length_modulation_per_v,
            "mosfet.channel_length_modulation_per_v",
        )
        nonnegative_number(self.drain_resistance_ohm, "mosfet.drain_resistance_ohm")
        nonnegative_number(self.source_resistance_ohm, "mosfet.source_resistance_ohm")
        for name in ("external_cgs_f", "external_cgd_f", "external_cds_f"):
            nonnegative_number(getattr(self, name), f"mosfet.{name}")
        if threshold >= 12.0:
            raise ValueError("mosfet.threshold_voltage_v must stay below the 12 V bus voltage")

    @property
    def width_over_length(self) -> float:
        return self.channel_width_m / self.channel_length_m

    def spice_parameters(self) -> dict[str, float]:
        """返回 Level 1 模型参数（GAMMA 固定为 0，体端接源极）。"""
        return {
            "LEVEL": float(self.level),
            "VTO": self.threshold_voltage_v,
            "KP": self.kp_a_per_v2,
            "LAMBDA": self.channel_length_modulation_per_v,
            "RD": self.drain_resistance_ohm,
            "RS": self.source_resistance_ohm,
            "GAMMA": 0.0,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_type": self.model_type,
            "level": self.level,
            "threshold_voltage_v": self.threshold_voltage_v,
            "kp_a_per_v2": self.kp_a_per_v2,
            "channel_length_m": self.channel_length_m,
            "channel_width_m": self.channel_width_m,
            "width_over_length": self.width_over_length,
            "channel_length_modulation_per_v": self.channel_length_modulation_per_v,
            "drain_resistance_ohm": self.drain_resistance_ohm,
            "source_resistance_ohm": self.source_resistance_ohm,
            "external_cgs_f": self.external_cgs_f,
            "external_cgd_f": self.external_cgd_f,
            "external_cds_f": self.external_cds_f,
            "model_source": self.model_source,
            "model_version": self.model_version,
            "spice_parameters": self.spice_parameters(),
            "limitations": (
                "Level 1 square-law teaching model; constant external capacitances; "
                "not a validated commercial power MOSFET model"
            ),
        }


@dataclass(frozen=True)
class DiodeModelConfig:
    """续流二极管非理想 ``D`` 模型参数。"""

    model_name: str = "DFREE_NONIDEAL"
    saturation_current_a: float = 1e-6
    ideality_factor: float = 1.0
    series_resistance_ohm: float = 0.015
    junction_capacitance_f: float = 200e-12
    junction_potential_v: float = 0.7
    grading_coefficient: float = 0.5
    transit_time_s: float = 0.0
    model_source: str = "educational_assumption"
    model_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("model_name", "model_source", "model_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"diode.{name} must be a non-empty string")
        positive_number(self.saturation_current_a, "diode.saturation_current_a")
        positive_number(self.ideality_factor, "diode.ideality_factor")
        nonnegative_number(self.series_resistance_ohm, "diode.series_resistance_ohm")
        nonnegative_number(self.junction_capacitance_f, "diode.junction_capacitance_f")
        positive_number(self.junction_potential_v, "diode.junction_potential_v")
        grading = finite_number(self.grading_coefficient, "diode.grading_coefficient")
        if not 0.0 < grading <= 1.0:
            raise ValueError("diode.grading_coefficient must be in (0, 1]")
        nonnegative_number(self.transit_time_s, "diode.transit_time_s")

    def spice_parameters(self) -> dict[str, float]:
        return {
            "IS": self.saturation_current_a,
            "N": self.ideality_factor,
            "RS": self.series_resistance_ohm,
            "CJO": self.junction_capacitance_f,
            "VJ": self.junction_potential_v,
            "M": self.grading_coefficient,
            "TT": self.transit_time_s,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "saturation_current_a": self.saturation_current_a,
            "ideality_factor": self.ideality_factor,
            "series_resistance_ohm": self.series_resistance_ohm,
            "junction_capacitance_f": self.junction_capacitance_f,
            "junction_potential_v": self.junction_potential_v,
            "grading_coefficient": self.grading_coefficient,
            "transit_time_s": self.transit_time_s,
            "model_source": self.model_source,
            "model_version": self.model_version,
            "spice_parameters": self.spice_parameters(),
            "limitations": (
                "low charge-storage teaching diode; not a validated Schottky model; "
                "reverse recovery is not physically calibrated"
            ),
        }


@dataclass(frozen=True)
class InductorModelConfig:
    """理想电感 + 绕组直流电阻 DCR。"""

    inductance_h: float = 47e-6
    dcr_ohm: float = 0.05

    def __post_init__(self) -> None:
        positive_number(self.inductance_h, "inductor.inductance_h")
        nonnegative_number(self.dcr_ohm, "inductor.dcr_ohm")

    def to_dict(self) -> dict[str, float]:
        return {"inductance_h": self.inductance_h, "dcr_ohm": self.dcr_ohm}


@dataclass(frozen=True)
class CapacitorModelConfig:
    """理想电容 + 串联 ESR。"""

    capacitance_f: float = 100e-6
    esr_ohm: float = 0.03

    def __post_init__(self) -> None:
        positive_number(self.capacitance_f, "capacitor.capacitance_f")
        nonnegative_number(self.esr_ohm, "capacitor.esr_ohm")

    def to_dict(self) -> dict[str, float]:
        return {"capacitance_f": self.capacitance_f, "esr_ohm": self.esr_ohm}


@dataclass(frozen=True)
class GateDriverConfig:
    """理想浮动高侧栅极驱动参数。

    驱动命令以 MOSFET 源极（开关节点 ``sw``）为参考，
    ``drive_voltage_v`` 是 ``V(drv) - V(sw)`` 的高电平，不是对地电压。
    """

    drive_voltage_v: float = 10.0
    low_voltage_v: float = 0.0
    gate_resistance_ohm: float = 10.0
    gate_source_pulldown_ohm: float = 100_000.0
    rise_time_s: float = 20e-9
    fall_time_s: float = 20e-9
    delay_s: float = 10e-6
    driver_type: str = "ideal_floating_source"

    def __post_init__(self) -> None:
        if not isinstance(self.driver_type, str) or self.driver_type not in SUPPORTED_DRIVER_TYPES:
            raise ValueError(
                f"gate_driver.driver_type must be one of {SUPPORTED_DRIVER_TYPES}"
            )
        drive = finite_number(self.drive_voltage_v, "gate_driver.drive_voltage_v")
        low = finite_number(self.low_voltage_v, "gate_driver.low_voltage_v")
        if drive <= low:
            raise ValueError("gate_driver.drive_voltage_v must exceed low_voltage_v")
        if low < 0:
            raise ValueError("gate_driver.low_voltage_v must be nonnegative for this NMOS driver")
        resistance = positive_number(
            self.gate_resistance_ohm, "gate_driver.gate_resistance_ohm"
        )
        if not 0.1 <= resistance <= 1000.0:
            raise ValueError(
                "gate_driver.gate_resistance_ohm must be within [0.1, 1000] ohm, "
                f"got {resistance!r}"
            )
        positive_number(
            self.gate_source_pulldown_ohm, "gate_driver.gate_source_pulldown_ohm"
        )
        rise = positive_number(self.rise_time_s, "gate_driver.rise_time_s")
        fall = positive_number(self.fall_time_s, "gate_driver.fall_time_s")
        nonnegative_number(self.delay_s, "gate_driver.delay_s")
        if rise + fall >= 2.0 * 1e-3:
            raise ValueError("gate_driver edge times are unreasonably long")

    def validate_for_mosfet(self, mosfet: MosfetModelConfig) -> float:
        """校验驱动电压能在栅极建立足够过驱动，返回过驱动电压。"""
        if not isinstance(mosfet, MosfetModelConfig):
            raise ValueError("mosfet must be MosfetModelConfig")
        overdrive = self.drive_voltage_v - mosfet.threshold_voltage_v
        if overdrive <= 0:
            raise ValueError(
                "gate_driver.drive_voltage_v must exceed mosfet.threshold_voltage_v: "
                f"{self.drive_voltage_v!r} <= {mosfet.threshold_voltage_v!r}"
            )
        if self.low_voltage_v >= mosfet.threshold_voltage_v:
            raise ValueError("gate_driver.low_voltage_v must stay below the MOSFET threshold")
        return overdrive

    def to_dict(self) -> dict[str, Any]:
        return {
            "drive_voltage_v": self.drive_voltage_v,
            "low_voltage_v": self.low_voltage_v,
            "gate_resistance_ohm": self.gate_resistance_ohm,
            "gate_source_pulldown_ohm": self.gate_source_pulldown_ohm,
            "rise_time_s": self.rise_time_s,
            "fall_time_s": self.fall_time_s,
            "delay_s": self.delay_s,
            "driver_type": self.driver_type,
            "note": (
                "ideal floating source referenced to the switch node; "
                "no bootstrap charging, UVLO or gate-driver supply model"
            ),
        }


@dataclass(frozen=True)
class NonidealBuckConfig:
    """第四阶段非理想 Buck 完整参数集合。"""

    inductor: InductorModelConfig
    capacitor: CapacitorModelConfig
    mosfet: MosfetModelConfig
    diode: DiodeModelConfig
    gate_driver: GateDriverConfig
    transient: TransientConfig
    steady_state: SteadyStateConfig
    input_voltage_v: float = 12.0
    target_output_voltage_v: float = 5.0
    rated_output_current_a: float = 2.0
    switching_frequency_hz: float = 100_000.0
    duty_cycle: float = 5.0 / 12.0
    load_resistance_ohm: float = 2.5
    version: str = "1.0"
    circuit_name: str = "Nonideal MOSFET Buck"
    topology: str = "asynchronous_buck"
    control_mode: str = "open_loop_pwm"
    model_variant: str = "E"
    specification_type: str = "project_assumption"

    def __post_init__(self) -> None:
        for name, value_type in (
            ("inductor", InductorModelConfig),
            ("capacitor", CapacitorModelConfig),
            ("mosfet", MosfetModelConfig),
            ("diode", DiodeModelConfig),
            ("gate_driver", GateDriverConfig),
            ("transient", TransientConfig),
            ("steady_state", SteadyStateConfig),
        ):
            if not isinstance(getattr(self, name), value_type):
                raise ValueError(f"{name} must be {value_type.__name__}")

        vin = positive_number(self.input_voltage_v, "circuit.input_voltage_v")
        target = positive_number(
            self.target_output_voltage_v, "circuit.target_output_voltage_v"
        )
        if target >= vin:
            raise ValueError("circuit.target_output_voltage_v must be lower than input voltage")
        positive_number(self.rated_output_current_a, "circuit.rated_output_current_a")
        positive_number(self.switching_frequency_hz, "circuit.switching_frequency_hz")
        positive_number(self.load_resistance_ohm, "circuit.load_resistance_ohm")
        duty = finite_number(self.duty_cycle, "circuit.duty_cycle")
        if not 0.0 < duty < 1.0:
            raise ValueError("circuit.duty_cycle must be in (0, 1)")
        variant = str(self.model_variant).strip().upper()
        if variant not in ("A", "B", "C", "D", "E"):
            raise ValueError("model_variant must be one of A, B, C, D, E")
        for name in (
            "version",
            "circuit_name",
            "topology",
            "control_mode",
            "specification_type",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

        self.gate_driver.validate_for_mosfet(self.mosfet)
        self.transient.validate_for_switching(self.switching_frequency_hz)
        if self.gate_driver.delay_s >= self.transient.end_time_s:
            raise ValueError("gate_driver.delay_s must be shorter than the simulated end time")

    @property
    def period_s(self) -> float:
        return 1.0 / self.switching_frequency_hz

    @property
    def ideal_duty_cycle(self) -> float:
        return self.target_output_voltage_v / self.input_voltage_v

    @property
    def pwm(self) -> PWMParameters:
        """栅极驱动命令的 PWM 参数（高电平为驱动器输出电压）。"""
        return PWMParameters(
            frequency_hz=self.switching_frequency_hz,
            duty_cycle=self.duty_cycle,
            low_voltage_v=self.gate_driver.low_voltage_v,
            high_voltage_v=self.gate_driver.drive_voltage_v,
            rise_time_s=self.gate_driver.rise_time_s,
            fall_time_s=self.gate_driver.fall_time_s,
            delay_s=self.gate_driver.delay_s,
        )

    def with_dcr(self, dcr_ohm: float) -> "NonidealBuckConfig":
        return replace(
            self,
            inductor=replace(self.inductor, dcr_ohm=nonnegative_number(dcr_ohm, "dcr_ohm")),
        )

    def with_esr(self, esr_ohm: float) -> "NonidealBuckConfig":
        return replace(
            self,
            capacitor=replace(self.capacitor, esr_ohm=nonnegative_number(esr_ohm, "esr_ohm")),
        )

    def with_variant(self, variant: str) -> "NonidealBuckConfig":
        return replace(self, model_variant=str(variant).strip().upper())

    def with_duty(self, duty_cycle: float) -> "NonidealBuckConfig":
        return replace(self, duty_cycle=finite_number(duty_cycle, "duty_cycle"))

    def with_transient(self, **overrides: float) -> "NonidealBuckConfig":
        return replace(self, transient=replace(self.transient, **overrides))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "circuit": {
                "name": self.circuit_name,
                "topology": self.topology,
                "control_mode": self.control_mode,
                "model_variant": self.model_variant,
                "input_voltage_v": self.input_voltage_v,
                "target_output_voltage_v": self.target_output_voltage_v,
                "rated_output_current_a": self.rated_output_current_a,
                "switching_frequency_hz": self.switching_frequency_hz,
                "duty_cycle": self.duty_cycle,
                "load_resistance_ohm": self.load_resistance_ohm,
                "period_s": self.period_s,
                "ideal_duty_cycle": self.ideal_duty_cycle,
            },
            "inductor": self.inductor.to_dict(),
            "capacitor": self.capacitor.to_dict(),
            "mosfet": self.mosfet.to_dict(),
            "diode": self.diode.to_dict(),
            "gate_driver": self.gate_driver.to_dict(),
            "simulation": self.transient.to_dict(),
            "steady_state": self.steady_state.to_dict(),
            "metadata": {
                "specification_type": self.specification_type,
                "data_source": "spice_simulation",
            },
        }


# --------------------------------------------------------------------- loaders
def _section(payload: dict[str, Any], key: str, where: str = "config") -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"缺少配置段: {where}.{key}")
    return value


def _value(section: dict[str, Any], key: str, where: str) -> Any:
    if key not in section:
        raise ValueError(f"配置缺少字段: {where}.{key}")
    return section[key]


def _read_yaml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件根节点必须是映射: {config_path}")
    return payload


def mosfet_config_from_mapping(payload: dict[str, Any], *, where: str = "mosfet") -> MosfetModelConfig:
    if not isinstance(payload, dict):
        raise ValueError(f"{where} must be a mapping")
    return MosfetModelConfig(
        model_name=_value(payload, "model_name", where),
        model_type=_value(payload, "model_type", where),
        level=_value(payload, "level", where),
        threshold_voltage_v=_value(payload, "threshold_voltage_v", where),
        kp_a_per_v2=_value(payload, "kp_a_per_v2", where),
        channel_length_m=_value(payload, "channel_length_m", where),
        channel_width_m=_value(payload, "channel_width_m", where),
        channel_length_modulation_per_v=_value(
            payload, "channel_length_modulation_per_v", where
        ),
        drain_resistance_ohm=_value(payload, "drain_resistance_ohm", where),
        source_resistance_ohm=_value(payload, "source_resistance_ohm", where),
        external_cgs_f=_value(payload, "external_cgs_f", where),
        external_cgd_f=_value(payload, "external_cgd_f", where),
        external_cds_f=_value(payload, "external_cds_f", where),
        model_source=_value(payload, "model_source", where),
        model_version=payload.get("model_version", "1.0"),
    )


def diode_config_from_mapping(payload: dict[str, Any], *, where: str = "diode") -> DiodeModelConfig:
    if not isinstance(payload, dict):
        raise ValueError(f"{where} must be a mapping")
    return DiodeModelConfig(
        model_name=_value(payload, "model_name", where),
        saturation_current_a=_value(payload, "saturation_current_a", where),
        ideality_factor=_value(payload, "ideality_factor", where),
        series_resistance_ohm=_value(payload, "series_resistance_ohm", where),
        junction_capacitance_f=_value(payload, "junction_capacitance_f", where),
        junction_potential_v=_value(payload, "junction_potential_v", where),
        grading_coefficient=_value(payload, "grading_coefficient", where),
        transit_time_s=_value(payload, "transit_time_s", where),
        model_source=_value(payload, "model_source", where),
        model_version=payload.get("model_version", "1.0"),
    )


def gate_driver_config_from_mapping(
    payload: dict[str, Any], *, where: str = "gate_driver"
) -> GateDriverConfig:
    if not isinstance(payload, dict):
        raise ValueError(f"{where} must be a mapping")
    return GateDriverConfig(
        drive_voltage_v=_value(payload, "drive_voltage_v", where),
        low_voltage_v=_value(payload, "low_voltage_v", where),
        gate_resistance_ohm=_value(payload, "gate_resistance_ohm", where),
        gate_source_pulldown_ohm=_value(payload, "gate_source_pulldown_ohm", where),
        rise_time_s=_value(payload, "rise_time_s", where),
        fall_time_s=_value(payload, "fall_time_s", where),
        delay_s=_value(payload, "delay_s", where),
        driver_type=_value(payload, "driver_type", where),
    )


def transient_config_from_mapping(
    payload: dict[str, Any], *, where: str = "simulation"
) -> TransientConfig:
    if not isinstance(payload, dict):
        raise ValueError(f"{where} must be a mapping")
    return TransientConfig(
        temperature_c=_value(payload, "temperature_c", where),
        nominal_temperature_c=_value(payload, "nominal_temperature_c", where),
        step_time_s=_value(payload, "step_time_s", where),
        max_step_time_s=_value(payload, "max_step_time_s", where),
        end_time_s=_value(payload, "end_time_s", where),
    )


def steady_state_config_from_mapping(
    payload: dict[str, Any], *, where: str = "steady_state"
) -> SteadyStateConfig:
    if not isinstance(payload, dict):
        raise ValueError(f"{where} must be a mapping")
    return SteadyStateConfig(
        minimum_cycles=_value(payload, "minimum_cycles", where),
        comparison_cycles=_value(payload, "comparison_cycles", where),
        relative_mean_tolerance=_value(payload, "relative_mean_tolerance", where),
        ripple_relative_tolerance=_value(payload, "ripple_relative_tolerance", where),
        absolute_voltage_tolerance_v=_value(payload, "absolute_voltage_tolerance_v", where),
        absolute_current_tolerance_a=_value(payload, "absolute_current_tolerance_a", where),
        absolute_ripple_tolerance_v=_value(payload, "absolute_ripple_tolerance_v", where),
    )


DEFAULT_STEADY_STATE = SteadyStateConfig()


def load_nonideal_buck_config(
    path: str | Path | None = None,
) -> NonidealBuckConfig:
    """读取并校验非理想 Buck 配置。"""
    payload = _read_yaml(path or DEFAULT_NONIDEAL_CONFIG_PATH)
    circuit = _section(payload, "circuit")
    inductor_payload = _section(payload, "circuit")
    capacitor_payload = _section(payload, "circuit")
    simulation = _section(payload, "simulation")

    return NonidealBuckConfig(
        inductor=InductorModelConfig(
            inductance_h=_value(inductor_payload, "inductance_h", "circuit"),
            dcr_ohm=_value(inductor_payload, "inductor_dcr_ohm", "circuit"),
        ),
        capacitor=CapacitorModelConfig(
            capacitance_f=_value(capacitor_payload, "capacitance_f", "circuit"),
            esr_ohm=_value(capacitor_payload, "capacitor_esr_ohm", "circuit"),
        ),
        mosfet=mosfet_config_from_mapping(_section(payload, "mosfet")),
        diode=diode_config_from_mapping(_section(payload, "diode")),
        gate_driver=gate_driver_config_from_mapping(_section(payload, "gate_driver")),
        transient=transient_config_from_mapping(simulation),
        steady_state=(
            steady_state_config_from_mapping(_section(payload, "steady_state"))
            if "steady_state" in payload
            else DEFAULT_STEADY_STATE
        ),
        input_voltage_v=_value(circuit, "input_voltage_v", "circuit"),
        target_output_voltage_v=_value(circuit, "target_output_voltage_v", "circuit"),
        rated_output_current_a=_value(circuit, "rated_output_current_a", "circuit"),
        switching_frequency_hz=_value(circuit, "switching_frequency_hz", "circuit"),
        duty_cycle=_value(circuit, "duty_cycle", "circuit"),
        load_resistance_ohm=_value(circuit, "load_resistance_ohm", "circuit"),
        version=payload.get("version", "1.0"),
        circuit_name=_value(circuit, "name", "circuit"),
        topology=_value(circuit, "topology", "circuit"),
        control_mode=_value(circuit, "control_mode", "circuit"),
        model_variant=payload.get("model_variant", "E"),
        specification_type=_section(payload, "metadata").get(
            "specification_type", "project_assumption"
        )
        if "metadata" in payload
        else "project_assumption",
    )


def load_device_models(path: str | Path | None = None) -> dict[str, Any]:
    """读取器件测试台配置（MOSFET / 二极管 / 驱动 / 温度）。"""
    payload = _read_yaml(path or DEFAULT_DEVICE_MODELS_PATH)
    mosfet = mosfet_config_from_mapping(_section(payload, "mosfet"))
    diode = diode_config_from_mapping(_section(payload, "diode"))
    return {
        "version": payload.get("version", "1.0"),
        "mosfet": mosfet,
        "diode": diode,
        "mosfet_tests": _section(payload, "mosfet_tests", "device_models"),
        "diode_tests": _section(payload, "diode_tests", "device_models"),
        "gate_driver_tests": _section(payload, "gate_driver_tests", "device_models"),
        "temperature_tests": _section(payload, "temperature_tests", "device_models"),
        "raw": payload,
    }


def temperature_values(path: str | Path | None = None) -> tuple[float, ...]:
    payload = _read_yaml(path or DEFAULT_DEVICE_MODELS_PATH)
    values = payload.get("temperature_tests", {}).get("temperature_c")
    if not isinstance(values, list) or not values:
        raise ValueError("device_models.temperature_tests.temperature_c must be a non-empty list")
    return tuple(temperature_celsius(value, "temperature_c") for value in values)


def load_validation_limits(path: str | Path | None = None) -> dict[str, Any]:
    """读取非理想 Buck 验收判据。"""
    payload = _read_yaml(path or DEFAULT_VALIDATION_PATH)
    for section in ("integration", "power", "losses", "device"):
        _section(payload, section, "validation")
    return payload

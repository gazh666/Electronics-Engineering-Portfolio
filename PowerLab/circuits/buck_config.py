"""Buck 变换器统一参数配置（SI 单位）。

所有数值都经过 :mod:`circuits.validators` 校验；YAML 加载缺失字段直接报错，
不使用默认值兜底，避免悄悄改变电路设计。

设计目标 ``target_output_voltage_v`` 与实际控制参数 ``duty_cycle`` 分开保存：
两者不一致时仍允许进行开环特性实验，但不会自动修改占空比。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .pwm import MIN_STEPS_PER_PERIOD, PWMParameters, validate_timing_resolution
from .switch_models import DiodeConfig, SwitchConfig
from .validators import (
    finite_number,
    positive_integer,
    positive_number,
    temperature_celsius,
    transient_parameters,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUCK_CONFIG_PATH = PROJECT_ROOT / "configs" / "buck_config.yaml"

#: 配置对象命名兼容别名（任务书使用 PWMConfig 名称）。
PWMConfig = PWMParameters


@dataclass(frozen=True)
class BuckConfig:
    """Buck 主电路参数：12 V → 5 V，100 kHz，47 µH，100 µF。"""

    input_voltage_v: float = 12.0
    target_output_voltage_v: float = 5.0
    rated_output_current_a: float = 2.0
    switching_frequency_hz: float = 100_000.0
    duty_cycle: float = 5.0 / 12.0
    inductance_h: float = 47e-6
    capacitance_f: float = 100e-6
    load_resistance_ohm: float = 2.5

    def __post_init__(self) -> None:
        for name in (
            "input_voltage_v",
            "target_output_voltage_v",
            "rated_output_current_a",
            "switching_frequency_hz",
            "inductance_h",
            "capacitance_f",
            "load_resistance_ohm",
        ):
            positive_number(getattr(self, name), f"buck.{name}")

        finite_number(self.duty_cycle, "buck.duty_cycle")
        if not 0 < self.duty_cycle < 1:
            raise ValueError(f"buck.duty_cycle must be in (0, 1), got {self.duty_cycle!r}")
        if self.target_output_voltage_v >= self.input_voltage_v:
            raise ValueError(
                "buck.target_output_voltage_v must be lower than input_voltage_v for a buck converter"
            )

    @property
    def period_s(self) -> float:
        return 1.0 / self.switching_frequency_hz

    @property
    def ideal_duty_cycle(self) -> float:
        return self.target_output_voltage_v / self.input_voltage_v

    @property
    def ideal_ccm_output_voltage_v(self) -> float:
        return self.duty_cycle * self.input_voltage_v

    def to_dict(self) -> dict[str, float]:
        return {
            "input_voltage_v": self.input_voltage_v,
            "target_output_voltage_v": self.target_output_voltage_v,
            "rated_output_current_a": self.rated_output_current_a,
            "switching_frequency_hz": self.switching_frequency_hz,
            "duty_cycle": self.duty_cycle,
            "inductance_h": self.inductance_h,
            "capacitance_f": self.capacitance_f,
            "load_resistance_ohm": self.load_resistance_ohm,
            "period_s": self.period_s,
            "ideal_duty_cycle": self.ideal_duty_cycle,
        }


@dataclass(frozen=True)
class TransientConfig:
    """瞬态分析参数；``step_time_s`` 是输出步长，``max_step_time_s`` 是内部最大步长。"""

    temperature_c: float = 25.0
    nominal_temperature_c: float = 25.0
    step_time_s: float = 100e-9
    max_step_time_s: float = 50e-9
    end_time_s: float = 5e-3

    def __post_init__(self) -> None:
        temperature_celsius(self.temperature_c, "simulation.temperature_c")
        temperature_celsius(self.nominal_temperature_c, "simulation.nominal_temperature_c")
        transient_parameters(self.step_time_s, self.end_time_s, 0.0, name="simulation")
        max_step = positive_number(self.max_step_time_s, "simulation.max_step_time_s")
        if max_step > self.step_time_s:
            raise ValueError(
                "simulation.max_step_time_s must not exceed step_time_s: "
                f"{max_step!r} > {self.step_time_s!r}"
            )

    def validate_for_switching(self, switching_frequency_hz: float) -> float:
        """校验最大步长能解析开关周期，返回每周期步数。"""
        return validate_timing_resolution(switching_frequency_hz, self.max_step_time_s)

    def to_dict(self) -> dict[str, float]:
        return {
            "temperature_c": self.temperature_c,
            "nominal_temperature_c": self.nominal_temperature_c,
            "step_time_s": self.step_time_s,
            "max_step_time_s": self.max_step_time_s,
            "end_time_s": self.end_time_s,
        }


@dataclass(frozen=True)
class SteadyStateConfig:
    """稳态窗口判定条件（相对 + 绝对容差组合）。"""

    minimum_cycles: int = 20
    comparison_cycles: int = 10
    relative_mean_tolerance: float = 0.001
    ripple_relative_tolerance: float = 0.05
    absolute_voltage_tolerance_v: float = 0.001
    absolute_current_tolerance_a: float = 0.001
    absolute_ripple_tolerance_v: float = 0.0005

    def __post_init__(self) -> None:
        positive_integer(self.minimum_cycles, "steady_state.minimum_cycles", minimum=1)
        positive_integer(self.comparison_cycles, "steady_state.comparison_cycles", minimum=1)
        if self.minimum_cycles < 2 * self.comparison_cycles:
            raise ValueError(
                "steady_state.minimum_cycles must be at least 2 * comparison_cycles"
            )
        for name in ("relative_mean_tolerance", "ripple_relative_tolerance"):
            value = finite_number(getattr(self, name), f"steady_state.{name}")
            if not 0 < value < 1:
                raise ValueError(f"steady_state.{name} must be in (0, 1), got {value!r}")
        positive_number(
            self.absolute_voltage_tolerance_v, "steady_state.absolute_voltage_tolerance_v"
        )
        positive_number(
            self.absolute_current_tolerance_a, "steady_state.absolute_current_tolerance_a"
        )
        positive_number(
            self.absolute_ripple_tolerance_v, "steady_state.absolute_ripple_tolerance_v"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_cycles": self.minimum_cycles,
            "comparison_cycles": self.comparison_cycles,
            "relative_mean_tolerance": self.relative_mean_tolerance,
            "ripple_relative_tolerance": self.ripple_relative_tolerance,
            "absolute_voltage_tolerance_v": self.absolute_voltage_tolerance_v,
            "absolute_current_tolerance_a": self.absolute_current_tolerance_a,
            "absolute_ripple_tolerance_v": self.absolute_ripple_tolerance_v,
        }


@dataclass(frozen=True)
class BuckParameters:
    """Buck 完整参数集合：电路 + PWM + 开关 + 二极管 + 仿真 + 稳态判据。"""

    circuit: BuckConfig
    pwm: PWMParameters
    switch: SwitchConfig
    diode: DiodeConfig
    transient: TransientConfig
    steady_state: SteadyStateConfig
    version: str = "1.0"
    circuit_name: str = "Basic Asynchronous Buck"
    topology: str = "asynchronous_buck"
    control_mode: str = "open_loop_pwm"
    model_type: str = "near_ideal_switch"

    def __post_init__(self) -> None:
        if not isinstance(self.circuit, BuckConfig):
            raise ValueError("circuit must be BuckConfig")
        if not isinstance(self.pwm, PWMParameters):
            raise ValueError("pwm must be PWMParameters")
        if not isinstance(self.switch, SwitchConfig):
            raise ValueError("switch must be SwitchConfig")
        if not isinstance(self.diode, DiodeConfig):
            raise ValueError("diode must be DiodeConfig")
        if not isinstance(self.transient, TransientConfig):
            raise ValueError("transient must be TransientConfig")
        if not isinstance(self.steady_state, SteadyStateConfig):
            raise ValueError("steady_state must be SteadyStateConfig")
        for name, value in (
            ("version", self.version),
            ("circuit_name", self.circuit_name),
            ("topology", self.topology),
            ("control_mode", self.control_mode),
            ("model_type", self.model_type),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

        if not math.isclose(
            self.pwm.frequency_hz,
            self.circuit.switching_frequency_hz,
            rel_tol=1e-12,
            abs_tol=0.0,
        ):
            raise ValueError(
                "pwm.frequency_hz must equal buck.switching_frequency_hz: "
                f"{self.pwm.frequency_hz!r} != {self.circuit.switching_frequency_hz!r}"
            )
        self.switch.validate_gate_levels(self.pwm.low_voltage_v, self.pwm.high_voltage_v)
        self.transient.validate_for_switching(self.circuit.switching_frequency_hz)
        if self.pwm.delay_s >= self.transient.end_time_s:
            raise ValueError("pwm.delay_s must be shorter than the simulated end time")

    @property
    def minimum_steps_per_period(self) -> float:
        return self.circuit.period_s / self.transient.max_step_time_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "circuit": {
                **self.circuit.to_dict(),
                "name": self.circuit_name,
                "topology": self.topology,
                "control_mode": self.control_mode,
                "model_type": self.model_type,
            },
            "pwm": self.pwm.to_dict(),
            "switch": self.switch.to_dict(),
            "diode": self.diode.to_dict(),
            "simulation": {
                **self.transient.to_dict(),
                "minimum_steps_per_period": self.minimum_steps_per_period,
                "required_minimum_steps_per_period": MIN_STEPS_PER_PERIOD,
            },
            "steady_state": self.steady_state.to_dict(),
        }


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Buck 配置缺少映射段: {key}")
    return value


def _value(section: dict[str, Any], key: str, where: str) -> Any:
    if key not in section:
        raise ValueError(f"Buck 配置缺少字段: {where}.{key}")
    return section[key]


def load_buck_config(path: str | Path = DEFAULT_BUCK_CONFIG_PATH) -> BuckParameters:
    """读取并校验 ``configs/buck_config.yaml``。"""
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件根节点必须是映射: {config_path}")

    circuit_raw = _section(payload, "circuit")
    pwm_raw = _section(payload, "pwm")
    switch_raw = _section(payload, "switch")
    diode_raw = _section(payload, "diode")
    sim_raw = _section(payload, "simulation")
    steady_raw = _section(payload, "steady_state")

    switching_frequency = _value(circuit_raw, "switching_frequency_hz", "circuit")
    duty_cycle = _value(circuit_raw, "duty_cycle", "circuit")

    circuit = BuckConfig(
        input_voltage_v=_value(circuit_raw, "input_voltage_v", "circuit"),
        target_output_voltage_v=_value(circuit_raw, "target_output_voltage_v", "circuit"),
        rated_output_current_a=_value(circuit_raw, "rated_output_current_a", "circuit"),
        switching_frequency_hz=switching_frequency,
        duty_cycle=duty_cycle,
        inductance_h=_value(circuit_raw, "inductance_h", "circuit"),
        capacitance_f=_value(circuit_raw, "capacitance_f", "circuit"),
        load_resistance_ohm=_value(circuit_raw, "load_resistance_ohm", "circuit"),
    )
    pwm = PWMParameters(
        frequency_hz=switching_frequency,
        duty_cycle=duty_cycle,
        low_voltage_v=_value(pwm_raw, "low_voltage_v", "pwm"),
        high_voltage_v=_value(pwm_raw, "high_voltage_v", "pwm"),
        rise_time_s=_value(pwm_raw, "rise_time_s", "pwm"),
        fall_time_s=_value(pwm_raw, "fall_time_s", "pwm"),
        delay_s=_value(pwm_raw, "delay_s", "pwm"),
    )
    switch = SwitchConfig(
        on_resistance_ohm=_value(switch_raw, "on_resistance_ohm", "switch"),
        off_resistance_ohm=_value(switch_raw, "off_resistance_ohm", "switch"),
        threshold_voltage_v=_value(switch_raw, "threshold_voltage_v", "switch"),
        hysteresis_voltage_v=_value(switch_raw, "hysteresis_voltage_v", "switch"),
    )
    diode = DiodeConfig(
        model_name=_value(diode_raw, "model_name", "diode"),
        saturation_current_a=_value(diode_raw, "saturation_current_a", "diode"),
        ideality_factor=_value(diode_raw, "ideality_factor", "diode"),
        series_resistance_ohm=_value(diode_raw, "series_resistance_ohm", "diode"),
    )
    transient = TransientConfig(
        temperature_c=_value(sim_raw, "temperature_c", "simulation"),
        nominal_temperature_c=_value(sim_raw, "nominal_temperature_c", "simulation"),
        step_time_s=_value(sim_raw, "step_time_s", "simulation"),
        max_step_time_s=_value(sim_raw, "max_step_time_s", "simulation"),
        end_time_s=_value(sim_raw, "end_time_s", "simulation"),
    )
    steady_state = SteadyStateConfig(
        minimum_cycles=_value(steady_raw, "minimum_cycles", "steady_state"),
        comparison_cycles=_value(steady_raw, "comparison_cycles", "steady_state"),
        relative_mean_tolerance=_value(steady_raw, "relative_mean_tolerance", "steady_state"),
        ripple_relative_tolerance=_value(steady_raw, "ripple_relative_tolerance", "steady_state"),
        absolute_voltage_tolerance_v=_value(
            steady_raw, "absolute_voltage_tolerance_v", "steady_state"
        ),
        absolute_current_tolerance_a=_value(
            steady_raw, "absolute_current_tolerance_a", "steady_state"
        ),
        absolute_ripple_tolerance_v=_value(
            steady_raw, "absolute_ripple_tolerance_v", "steady_state"
        ),
    )

    return BuckParameters(
        circuit=circuit,
        pwm=pwm,
        switch=switch,
        diode=diode,
        transient=transient,
        steady_state=steady_state,
        version=str(_value(payload, "version", "root")),
        circuit_name=str(_value(circuit_raw, "name", "circuit")),
        topology=str(_value(circuit_raw, "topology", "circuit")),
        control_mode=str(_value(circuit_raw, "control_mode", "circuit")),
        model_type=str(_value(circuit_raw, "model_type", "circuit")),
    )

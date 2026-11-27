"""第七阶段闭环 Buck 配置：功率级 + 控制器 + 软启动 + 扰动 + 仿真时间。

本模块只做参数定义、校验、YAML 读取与快照导出，不构建电路、不执行仿真。
功率级参数复用第四阶段 ``configs/nonideal_buck_config.yaml``，不在此重复定义，
避免同一器件参数出现两份不一致的副本。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from control.models import CarrierConfig, ControllerConfig, SoftStartConfig

from .buck_config import TransientConfig
from .dynamic_load import CurrentStepLoad, ResistiveStepLoad, load_from_dict
from .input_disturbance import LineStepCase
from .nonideal_config import NonidealBuckConfig, load_nonideal_buck_config
from .validators import finite_number, positive_number, temperature_celsius

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLOSED_LOOP_CONFIG_PATH = PROJECT_ROOT / "configs" / "closed_loop_config.yaml"
DEFAULT_CONTROLLER_CONFIG_PATH = PROJECT_ROOT / "configs" / "controller_config.yaml"
DEFAULT_DISTURBANCE_CONFIG_PATH = PROJECT_ROOT / "configs" / "disturbance_cases.yaml"

#: 闭环电路支持的功率级模型：E/D 为第四阶段 MOSFET 非理想模型，SW 为最小开关模型。
SUPPORTED_CLOSED_LOOP_VARIANTS = ("E", "D", "SW")
SUPPORTED_MODES = ("closed_loop", "open_loop")

LoadType = CurrentStepLoad | ResistiveStepLoad


@dataclass(frozen=True)
class ClosedLoopConfig:
    """一次闭环（或开环对照）仿真的完整配置。"""

    power_stage: NonidealBuckConfig
    controller: ControllerConfig
    soft_start: SoftStartConfig
    carrier: CarrierConfig
    line: LineStepCase
    load: LoadType | None = None
    variant: str = "E"
    open_loop_duty_cycle: float = 0.437
    end_time_s: float = 0.012
    step_time_s: float = 100e-9
    max_step_time_s: float = 100e-9
    temperature_c: float = 25.0
    name: str = "closed_loop_nominal"

    def __post_init__(self) -> None:
        if not isinstance(self.power_stage, NonidealBuckConfig):
            raise ValueError("power_stage must be NonidealBuckConfig")
        for value, expected, label in (
            (self.controller, ControllerConfig, "controller"),
            (self.soft_start, SoftStartConfig, "soft_start"),
            (self.carrier, CarrierConfig, "carrier"),
            (self.line, LineStepCase, "line"),
        ):
            if not isinstance(value, expected):
                raise ValueError(f"{label} must be {expected.__name__}")
        if self.load is not None and not isinstance(
            self.load, (CurrentStepLoad, ResistiveStepLoad)
        ):
            raise ValueError("load must be CurrentStepLoad, ResistiveStepLoad or None")
        variant = str(self.variant).strip().upper()
        if variant not in SUPPORTED_CLOSED_LOOP_VARIANTS:
            raise ValueError(
                f"variant must be one of {SUPPORTED_CLOSED_LOOP_VARIANTS}, got {self.variant!r}"
            )
        duty = finite_number(self.open_loop_duty_cycle, "open_loop_duty_cycle")
        if not 0.0 < duty < 1.0:
            raise ValueError("open_loop_duty_cycle must be in (0, 1)")
        end = positive_number(self.end_time_s, "end_time_s")
        step = positive_number(self.step_time_s, "step_time_s")
        max_step = positive_number(self.max_step_time_s, "max_step_time_s")
        if max_step > step:
            raise ValueError("max_step_time_s must not exceed step_time_s")
        if not 0.0 < step < end:
            raise ValueError("step_time_s must be smaller than end_time_s")
        temperature_celsius(self.temperature_c, "temperature_c")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        # 扰动事件必须完整落在仿真窗口内。
        self.line.pwl_points(end)
        if isinstance(self.load, CurrentStepLoad):
            self.load.pwl_points(end)
        elif isinstance(self.load, ResistiveStepLoad):
            if not (0.0 <= self.load.step_time_s < self.load.release_time_s <= end):
                raise ValueError(
                    "resistive load step/release must fall inside the simulation window"
                )
        if self.carrier.frequency_hz != self.power_stage.switching_frequency_hz:
            raise ValueError("carrier.frequency_hz must equal the power stage switching frequency")

    # ----------------------------------------------------------- derived
    @property
    def target_voltage_v(self) -> float:
        return self.power_stage.target_output_voltage_v

    @property
    def switching_frequency_hz(self) -> float:
        return self.power_stage.switching_frequency_hz

    @property
    def period_s(self) -> float:
        return 1.0 / self.switching_frequency_hz

    def transient_config(self) -> TransientConfig:
        """返回与当前闭环时间参数一致的第四阶段瞬态配置。"""
        return TransientConfig(
            temperature_c=self.temperature_c,
            nominal_temperature_c=self.temperature_c,
            step_time_s=self.step_time_s,
            max_step_time_s=self.max_step_time_s,
            end_time_s=self.end_time_s,
        )

    # ------------------------------------------------------------ mutators
    def with_timing(
        self,
        end_time_s: float,
        *,
        step_time_s: float | None = None,
        max_step_time_s: float | None = None,
    ) -> "ClosedLoopConfig":
        end = positive_number(end_time_s, "end_time_s")
        step = self.step_time_s if step_time_s is None else positive_number(
            step_time_s, "step_time_s"
        )
        max_step = (
            min(self.max_step_time_s, step)
            if max_step_time_s is None
            else positive_number(max_step_time_s, "max_step_time_s")
        )
        return replace(
            self,
            end_time_s=end,
            step_time_s=step,
            max_step_time_s=max_step,
            power_stage=replace(
                self.power_stage,
                transient=TransientConfig(
                    temperature_c=self.temperature_c,
                    nominal_temperature_c=self.temperature_c,
                    step_time_s=step,
                    max_step_time_s=max_step,
                    end_time_s=end,
                ),
            ),
        )

    def with_controller(self, controller: ControllerConfig) -> "ClosedLoopConfig":
        return replace(self, controller=controller)

    def with_gains(self, kp: float, ki: float) -> "ClosedLoopConfig":
        return replace(
            self,
            controller=replace(self.controller, kp=kp, ki=ki),
        )

    def with_anti_windup(self, method: str) -> "ClosedLoopConfig":
        return replace(
            self,
            controller=replace(self.controller, anti_windup=method),
        )

    def with_soft_start(
        self, duration_s: float, *, enabled: bool = True
    ) -> "ClosedLoopConfig":
        return replace(
            self,
            soft_start=replace(
                self.soft_start, enabled=enabled, duration_s=float(duration_s)
            ),
        )

    def with_load(self, load: LoadType | None) -> "ClosedLoopConfig":
        return replace(self, load=load)

    def with_named_load(self, name: str) -> "ClosedLoopConfig":
        """按 ``disturbance_cases.yaml`` 中的名称选择负载。"""
        return replace(self, load=load_disturbance_cases().load(name))

    def with_line(self, line: LineStepCase) -> "ClosedLoopConfig":
        return replace(self, line=line)

    def with_named_line(self, name: str) -> "ClosedLoopConfig":
        """按 ``disturbance_cases.yaml`` 中的名称选择输入工况。"""
        return replace(self, line=load_disturbance_cases().line(name))

    def with_variant(self, variant: str) -> "ClosedLoopConfig":
        return replace(self, variant=str(variant).strip().upper())

    def with_open_loop_duty(self, duty: float) -> "ClosedLoopConfig":
        return replace(self, open_loop_duty_cycle=finite_number(duty, "open_loop_duty_cycle"))

    def with_name(self, name: str) -> "ClosedLoopConfig":
        return replace(self, name=str(name).strip())

    # ------------------------------------------------------------- export
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "variant": self.variant,
            "target_voltage_v": self.target_voltage_v,
            "switching_frequency_hz": self.switching_frequency_hz,
            "open_loop_duty_cycle": self.open_loop_duty_cycle,
            "simulation": {
                "end_time_s": self.end_time_s,
                "step_time_s": self.step_time_s,
                "max_step_time_s": self.max_step_time_s,
                "temperature_c": self.temperature_c,
            },
            "power_stage": self.power_stage.to_dict(),
            "controller": self.controller.to_dict(),
            "soft_start": self.soft_start.to_dict(),
            "carrier": self.carrier.to_dict(),
            "line": self.line.to_dict(),
            "load": self.load.to_dict() if self.load is not None else {
                "load_type": "resistive_fixed",
                "resistance_ohm": self.power_stage.load_resistance_ohm,
            },
            "metadata": {
                "specification_type": "project_assumption",
                "data_source": "spice_simulation",
                "closed_loop_variant": self.variant,
            },
        }


# ------------------------------------------------------------------ loaders
def _read_yaml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件根节点必须是映射: {config_path}")
    return payload


def _resolve(path_value: str | Path) -> Path:
    candidate = Path(path_value)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def controller_config_from_mapping(payload: dict[str, Any]) -> ControllerConfig:
    if not isinstance(payload, dict):
        raise ValueError("controller configuration must be a mapping")
    return ControllerConfig(
        kp=payload["kp"],
        ki=payload["ki"],
        duty_min=payload.get("duty_min", 0.0),
        duty_max=payload.get("duty_max", 0.9),
        feedforward_enabled=bool(payload.get("feedforward_enabled", True)),
        anti_windup=payload.get("anti_windup", "back_calculation"),
        tracking_gain=payload.get("tracking_gain", 2000.0),
        vin_min_for_feedforward_v=payload.get("vin_min_for_feedforward_v", 2.0),
    )


def soft_start_config_from_mapping(payload: dict[str, Any]) -> SoftStartConfig:
    if not isinstance(payload, dict):
        raise ValueError("soft_start configuration must be a mapping")
    return SoftStartConfig(
        enabled=bool(payload.get("enabled", True)),
        duration_s=payload.get("duration_s", 0.002),
        initial_reference_v=payload.get("initial_reference_v", 0.0),
    )


def carrier_config_from_mapping(payload: dict[str, Any]) -> CarrierConfig:
    if not isinstance(payload, dict):
        raise ValueError("carrier configuration must be a mapping")
    return CarrierConfig(
        carrier_type=payload.get("carrier_type", "sine"),
        frequency_hz=payload["frequency_hz"],
        smoothing_width=payload.get("smoothing_width", 0.02),
        threshold=payload.get("threshold", 0.5),
    )


@dataclass(frozen=True)
class ControllerSettings:
    """controller_config.yaml 的完整内容（控制器 + 软启动 + 载波 + 设计记录）。"""

    controller: ControllerConfig
    soft_start: SoftStartConfig
    carrier: CarrierConfig
    design: dict[str, Any]
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "design": dict(self.design),
            "controller": self.controller.to_dict(),
            "soft_start": self.soft_start.to_dict(),
            "carrier": self.carrier.to_dict(),
        }


def load_controller_settings(
    path: str | Path | None = None,
) -> ControllerSettings:
    payload = _read_yaml(path or DEFAULT_CONTROLLER_CONFIG_PATH)
    return ControllerSettings(
        controller=controller_config_from_mapping(payload["controller"]),
        soft_start=soft_start_config_from_mapping(payload["soft_start"]),
        carrier=carrier_config_from_mapping(payload["carrier"]),
        design=dict(payload.get("design", {})),
        version=str(payload.get("version", "1.0")),
    )


@dataclass(frozen=True)
class DisturbanceCases:
    """disturbance_cases.yaml 的负载与输入工况集合。"""

    loads: dict[str, LoadType | None]
    lines: dict[str, LineStepCase]
    version: str = "1.0"

    def load(self, name: str) -> LoadType | None:
        if name not in self.loads:
            raise KeyError(f"unknown load case {name!r}; available: {tuple(self.loads)}")
        return self.loads[name]

    def line(self, name: str) -> LineStepCase:
        if name not in self.lines:
            raise KeyError(f"unknown line case {name!r}; available: {tuple(self.lines)}")
        return self.lines[name]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "loads": {
                key: (value.to_dict() if value is not None else None)
                for key, value in self.loads.items()
            },
            "lines": {key: value.to_dict() for key, value in self.lines.items()},
        }


def load_disturbance_cases(path: str | Path | None = None) -> DisturbanceCases:
    payload = _read_yaml(path or DEFAULT_DISTURBANCE_CONFIG_PATH)
    raw_loads = payload.get("loads", {})
    raw_lines = payload.get("lines", {})
    if not isinstance(raw_loads, dict) or not raw_loads:
        raise ValueError("disturbance_cases.loads must be a non-empty mapping")
    if not isinstance(raw_lines, dict) or not raw_lines:
        raise ValueError("disturbance_cases.lines must be a non-empty mapping")

    loads: dict[str, LoadType | None] = {}
    for name, item in raw_loads.items():
        loads[name] = None if item is None else load_from_dict(item)
    lines: dict[str, LineStepCase] = {}
    for name, item in raw_lines.items():
        if not isinstance(item, dict):
            raise ValueError(f"line case {name!r} must be a mapping")
        lines[name] = LineStepCase(
            name=item.get("name", name),
            vin_initial_v=item["vin_initial_v"],
            vin_final_v=item["vin_final_v"],
            step_time_s=item["step_time_s"],
            release_time_s=item.get("release_time_s"),
            transition_s=item.get("transition_s", 2e-5),
            vin_restore_v=item.get("vin_restore_v"),
        )
    return DisturbanceCases(
        loads=loads, lines=lines, version=str(payload.get("version", "1.0"))
    )


def load_closed_loop_config(
    path: str | Path | None = None,
    *,
    overrides: dict[str, Any] | None = None,
) -> ClosedLoopConfig:
    """读取闭环配置；``overrides`` 只允许覆盖时间/变体/占空比等顶层字段。"""
    payload = _read_yaml(path or DEFAULT_CLOSED_LOOP_CONFIG_PATH)
    power_stage = load_nonideal_buck_config(
        _resolve(payload.get("power_stage_config", "configs/nonideal_buck_config.yaml"))
    )
    settings = load_controller_settings(
        _resolve(payload.get("controller_config", "configs/controller_config.yaml"))
    )
    cases = load_disturbance_cases(
        _resolve(payload.get("disturbance_config", "configs/disturbance_cases.yaml"))
    )
    simulation = payload.get("simulation", {})
    if not isinstance(simulation, dict):
        raise ValueError("closed_loop_config.simulation must be a mapping")

    load_name = payload.get("load", "nominal")
    line_name = payload.get("line", "nominal")
    if load_name not in cases.loads:
        raise KeyError(f"unknown load case {load_name!r}; available: {tuple(cases.loads)}")
    if line_name not in cases.lines:
        raise KeyError(f"unknown line case {line_name!r}; available: {tuple(cases.lines)}")

    config = ClosedLoopConfig(
        power_stage=power_stage,
        controller=settings.controller,
        soft_start=settings.soft_start,
        carrier=settings.carrier,
        line=cases.lines[line_name],
        load=cases.loads[load_name],
        variant=payload.get("model_variant", "E"),
        open_loop_duty_cycle=payload.get("open_loop_duty_cycle", 0.437),
        end_time_s=simulation.get("end_time_s", 0.012),
        step_time_s=simulation.get("step_time_s", 100e-9),
        max_step_time_s=simulation.get("max_step_time_s", 100e-9),
        temperature_c=simulation.get("temperature_c", 25.0),
        name=payload.get("name", "closed_loop_nominal"),
    )
    if overrides:
        allowed = {
            "variant",
            "open_loop_duty_cycle",
            "end_time_s",
            "step_time_s",
            "max_step_time_s",
            "name",
            "load",
            "line",
        }
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(f"unsupported closed-loop overrides: {sorted(unknown)}")
        updates = dict(overrides)
        if "load" in updates and isinstance(updates["load"], str):
            updates["load"] = cases.load(updates["load"])
        if "line" in updates and isinstance(updates["line"], str):
            updates["line"] = cases.line(updates["line"])
        if "variant" in updates:
            updates["variant"] = str(updates["variant"]).strip().upper()
        max_step = updates.pop("max_step_time_s", None)
        step = updates.pop("step_time_s", None)
        end = updates.pop("end_time_s", None)
        config = replace(config, **updates)
        config = config.with_timing(
            end if end is not None else config.end_time_s,
            step_time_s=step,
            max_step_time_s=max_step,
        )
    return config


__all__ = [
    "SUPPORTED_CLOSED_LOOP_VARIANTS",
    "SUPPORTED_MODES",
    "ClosedLoopConfig",
    "ControllerSettings",
    "DisturbanceCases",
    "carrier_config_from_mapping",
    "controller_config_from_mapping",
    "load_closed_loop_config",
    "load_controller_settings",
    "load_disturbance_cases",
    "soft_start_config_from_mapping",
]

"""仿真配置的加载与校验。

配置来自 ``configs/simulation.yaml``；任何非法值都直接抛 ``ValueError``，
不允许静默回退到默认值。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from circuits.models import (
    AcSweepParameters,
    DcSweepParameters,
    DiodeParameters,
    RCParameters,
    RectifierParameters,
    RLParameters,
    RLCParameters,
    TransientParameters,
    VoltageDividerParameters,
    damping_cases,
)
from circuits.validators import finite_number, temperature_celsius

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "simulation.yaml"
DEFAULT_BASIC_CONFIG_PATH = PROJECT_ROOT / "configs" / "basic_circuits.yaml"


def _number(value: Any, name: str, *, strictly_positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是数值，实际为 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须是有限数，实际为 {value!r}")
    if strictly_positive and number <= 0:
        raise ValueError(f"{name} 必须是正数，实际为 {value!r}")
    return number


def _checkpoints(value: Any) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"rc.checkpoints_tau 必须是非空列表，实际为 {value!r}")
    points: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError(f"时间常数倍数必须是正整数，实际为 {item!r}")
        points.append(item)
    return tuple(points)


@dataclass(frozen=True)
class DividerConfig:
    vin_v: float = 12.0
    r1_ohm: float = 1_000.0
    r2_ohm: float = 1_000.0

    def __post_init__(self) -> None:
        _number(self.vin_v, "divider.vin_v", strictly_positive=True)
        _number(self.r1_ohm, "divider.r1_ohm", strictly_positive=True)
        _number(self.r2_ohm, "divider.r2_ohm", strictly_positive=True)

    @property
    def theoretical_output_v(self) -> float:
        return self.vin_v * self.r2_ohm / (self.r1_ohm + self.r2_ohm)

    @property
    def theoretical_current_a(self) -> float:
        return self.vin_v / (self.r1_ohm + self.r2_ohm)

    def to_dict(self) -> dict[str, float]:
        return {
            "vin_v": self.vin_v,
            "r1_ohm": self.r1_ohm,
            "r2_ohm": self.r2_ohm,
            "theoretical_output_v": self.theoretical_output_v,
            "theoretical_current_a": self.theoretical_current_a,
        }


@dataclass(frozen=True)
class RCConfig:
    vin_v: float = 5.0
    resistance_ohm: float = 1_000.0
    capacitance_f: float = 1e-6
    rise_time_s: float = 1e-6
    step_time_s: float = 1e-5
    end_time_s: float = 6e-3
    checkpoints_tau: tuple[int, ...] = (1, 2, 3, 5)

    def __post_init__(self) -> None:
        _number(self.vin_v, "rc.vin_v", strictly_positive=True)
        _number(self.resistance_ohm, "rc.resistance_ohm", strictly_positive=True)
        _number(self.capacitance_f, "rc.capacitance_f", strictly_positive=True)
        _number(self.rise_time_s, "rc.rise_time_s", strictly_positive=True)
        _number(self.step_time_s, "rc.step_time_s", strictly_positive=True)
        _number(self.end_time_s, "rc.end_time_s", strictly_positive=True)
        if self.step_time_s >= self.end_time_s:
            raise ValueError("rc.step_time_s 必须小于 rc.end_time_s")
        _checkpoints(list(self.checkpoints_tau))

    @property
    def tau_s(self) -> float:
        return self.resistance_ohm * self.capacitance_f

    def to_dict(self) -> dict[str, Any]:
        return {
            "vin_v": self.vin_v,
            "resistance_ohm": self.resistance_ohm,
            "capacitance_f": self.capacitance_f,
            "rise_time_s": self.rise_time_s,
            "step_time_s": self.step_time_s,
            "end_time_s": self.end_time_s,
            "tau_s": self.tau_s,
            "checkpoints_tau": list(self.checkpoints_tau),
        }


@dataclass(frozen=True)
class SimulationConfig:
    divider: DividerConfig
    rc: RCConfig

    def to_dict(self) -> dict[str, Any]:
        return {"divider": self.divider.to_dict(), "rc": self.rc.to_dict()}


def load_simulation_config(path: str | Path = DEFAULT_CONFIG_PATH) -> SimulationConfig:
    """从 YAML 读取并校验仿真配置。"""
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件根节点必须是映射: {config_path}")

    divider_raw = payload.get("divider")
    rc_raw = payload.get("rc")
    if not isinstance(divider_raw, dict):
        raise ValueError("缺少 divider 配置段")
    if not isinstance(rc_raw, dict):
        raise ValueError("缺少 rc 配置段")

    divider = DividerConfig(
        vin_v=divider_raw.get("vin_v"),
        r1_ohm=divider_raw.get("r1_ohm"),
        r2_ohm=divider_raw.get("r2_ohm"),
    )
    rc = RCConfig(
        vin_v=rc_raw.get("vin_v"),
        resistance_ohm=rc_raw.get("resistance_ohm"),
        capacitance_f=rc_raw.get("capacitance_f"),
        rise_time_s=rc_raw.get("rise_time_s"),
        step_time_s=rc_raw.get("step_time_s"),
        end_time_s=rc_raw.get("end_time_s"),
        checkpoints_tau=_checkpoints(rc_raw.get("checkpoints_tau")),
    )
    return SimulationConfig(divider=divider, rc=rc)


@dataclass(frozen=True)
class BasicCircuitsConfig:
    """第二阶段 11 项分析的完整配置。"""

    version: str
    simulation_temperature_c: float
    voltage_divider: VoltageDividerParameters
    divider_dc_sweep: DcSweepParameters
    rc: RCParameters
    rc_transient: TransientParameters
    rc_ac: AcSweepParameters
    rl: RLParameters
    rl_transient: TransientParameters
    rlc: RLCParameters
    rlc_damping_resistances_ohm: tuple[float, ...]
    rlc_transient: TransientParameters
    rlc_ac: AcSweepParameters
    diode: DiodeParameters
    diode_dc_sweep: DcSweepParameters
    rectifier: RectifierParameters
    rectifier_transient: TransientParameters

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string")
        temperature_celsius(self.simulation_temperature_c, "simulation_temperature_c")
        damping_cases(self.rlc_damping_resistances_ohm)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "simulation_temperature_c": self.simulation_temperature_c,
            "voltage_divider": {
                **self.voltage_divider.to_dict(),
                "dc_sweep": self.divider_dc_sweep.to_dict(),
            },
            "rc": {
                **self.rc.to_dict(),
                "transient": self.rc_transient.to_dict(),
                "ac": self.rc_ac.to_dict(),
            },
            "rl": {
                **self.rl.to_dict(),
                "transient": self.rl_transient.to_dict(),
            },
            "rlc": {
                **self.rlc.to_dict(),
                "damping_resistances_ohm": list(self.rlc_damping_resistances_ohm),
                "transient": self.rlc_transient.to_dict(),
                "ac": self.rlc_ac.to_dict(),
            },
            "diode": {
                **self.diode.to_dict(),
                "dc_sweep": self.diode_dc_sweep.to_dict(),
            },
            "rectifier": {
                **self.rectifier.to_dict(),
                "transient": self.rectifier_transient.to_dict(),
            },
        }


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"配置缺少映射段: {key}")
    return value


def _value(section: dict[str, Any], key: str, where: str) -> Any:
    if key not in section:
        raise ValueError(f"配置缺少字段: {where}.{key}")
    return section[key]


def _transient_from(section: dict[str, Any], where: str) -> TransientParameters:
    raw = _section(section, "transient")
    return TransientParameters(
        step_s=_value(raw, "step_s", f"{where}.transient"),
        end_s=_value(raw, "end_s", f"{where}.transient"),
    )


def _ac_from(section: dict[str, Any], where: str) -> AcSweepParameters:
    raw = _section(section, "ac")
    return AcSweepParameters(
        start_hz=_value(raw, "start_hz", f"{where}.ac"),
        stop_hz=_value(raw, "stop_hz", f"{where}.ac"),
        points_per_decade=_value(raw, "points_per_decade", f"{where}.ac"),
        variation=_value(raw, "variation", f"{where}.ac"),
    )


def _diode_from(section: dict[str, Any], where: str) -> DiodeParameters:
    return DiodeParameters(
        saturation_current_a=_value(section, "saturation_current_a", where),
        ideality_factor=_value(section, "ideality_factor", where),
        series_resistance_ohm=_value(section, "series_resistance_ohm", where),
        temperature_c=_value(section, "temperature_c", where),
    )


def load_basic_circuits_config(
    path: str | Path = DEFAULT_BASIC_CONFIG_PATH,
) -> BasicCircuitsConfig:
    """读取并校验 ``configs/basic_circuits.yaml``。

    缺失字段直接报错，不使用默认值兜底。
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件根节点必须是映射: {config_path}")

    divider_raw = _section(payload, "voltage_divider")
    divider_sweep_raw = _section(divider_raw, "dc_sweep")
    rc_raw = _section(payload, "rc")
    rl_raw = _section(payload, "rl")
    rlc_raw = _section(payload, "rlc")
    diode_raw = _section(payload, "diode")
    diode_sweep_raw = _section(diode_raw, "dc_sweep")
    rectifier_raw = _section(payload, "rectifier")

    damping_raw = _value(rlc_raw, "damping_resistances_ohm", "rlc")
    if not isinstance(damping_raw, (list, tuple)):
        raise ValueError("rlc.damping_resistances_ohm 必须是列表")
    damping = tuple(finite_number(value, "rlc.damping_resistances_ohm") for value in damping_raw)

    diode = _diode_from(diode_raw, "diode")

    config = BasicCircuitsConfig(
        version=_value(payload, "version", "root"),
        simulation_temperature_c=_value(payload, "simulation_temperature_c", "root"),
        voltage_divider=VoltageDividerParameters(
            vin_v=_value(divider_raw, "vin_v", "voltage_divider"),
            r1_ohm=_value(divider_raw, "r1_ohm", "voltage_divider"),
            r2_ohm=_value(divider_raw, "r2_ohm", "voltage_divider"),
        ),
        divider_dc_sweep=DcSweepParameters(
            start_v=_value(divider_sweep_raw, "start_v", "voltage_divider.dc_sweep"),
            stop_v=_value(divider_sweep_raw, "stop_v", "voltage_divider.dc_sweep"),
            step_v=_value(divider_sweep_raw, "step_v", "voltage_divider.dc_sweep"),
        ),
        rc=RCParameters(
            input_v=_value(rc_raw, "input_v", "rc"),
            resistance_ohm=_value(rc_raw, "resistance_ohm", "rc"),
            capacitance_f=_value(rc_raw, "capacitance_f", "rc"),
            rise_time_s=_value(rc_raw, "rise_time_s", "rc"),
        ),
        rc_transient=_transient_from(rc_raw, "rc"),
        rc_ac=_ac_from(rc_raw, "rc"),
        rl=RLParameters(
            input_v=_value(rl_raw, "input_v", "rl"),
            resistance_ohm=_value(rl_raw, "resistance_ohm", "rl"),
            inductance_h=_value(rl_raw, "inductance_h", "rl"),
            rise_time_s=_value(rl_raw, "rise_time_s", "rl"),
        ),
        rl_transient=_transient_from(rl_raw, "rl"),
        rlc=RLCParameters(
            input_v=_value(rlc_raw, "input_v", "rlc"),
            resistance_ohm=damping[0],
            inductance_h=_value(rlc_raw, "inductance_h", "rlc"),
            capacitance_f=_value(rlc_raw, "capacitance_f", "rlc"),
            rise_time_s=_value(rlc_raw, "rise_time_s", "rlc"),
        ),
        rlc_damping_resistances_ohm=damping,
        rlc_transient=_transient_from(rlc_raw, "rlc"),
        rlc_ac=_ac_from(rlc_raw, "rlc"),
        diode=diode,
        diode_dc_sweep=DcSweepParameters(
            start_v=_value(diode_sweep_raw, "start_v", "diode.dc_sweep"),
            stop_v=_value(diode_sweep_raw, "stop_v", "diode.dc_sweep"),
            step_v=_value(diode_sweep_raw, "step_v", "diode.dc_sweep"),
        ),
        rectifier=RectifierParameters(
            input_peak_v=_value(rectifier_raw, "input_peak_v", "rectifier"),
            frequency_hz=_value(rectifier_raw, "frequency_hz", "rectifier"),
            source_resistance_ohm=_value(rectifier_raw, "source_resistance_ohm", "rectifier"),
            load_resistance_ohm=_value(rectifier_raw, "load_resistance_ohm", "rectifier"),
            diode=diode,
        ),
        rectifier_transient=_transient_from(rectifier_raw, "rectifier"),
    )
    return config

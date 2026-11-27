"""统一电池模型参数：数据类、数值校验与 YAML 配置加载。

所有参数默认来自 ``configs/ecm_parameters.yaml``，其来源标记为
``educational_assumption``，不代表任何真实电芯参数辨识结果。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"


class ParameterError(ValueError):
    """参数非法。"""


def _real(value: Any, name: str) -> float:
    """转换为有限实数，拒绝布尔值、字符串数字与 NaN/Inf。"""
    if isinstance(value, bool):
        raise ParameterError(f"{name} 不允许使用布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ParameterError(f"{name} 必须是数值，实际为 {value!r}") from exc
    if not math.isfinite(number):
        raise ParameterError(f"{name} 必须是有限数值，实际为 {number!r}")
    return number


@dataclass(frozen=True)
class RCBranch:
    """一组并联 RC 极化支路。"""

    resistance_ohm: float
    capacitance_f: float

    def __post_init__(self) -> None:
        resistance = _real(self.resistance_ohm, "RC 支路电阻")
        capacitance = _real(self.capacitance_f, "RC 支路电容")
        if resistance <= 0.0:
            raise ParameterError("RC 支路电阻必须为正数")
        if capacitance <= 0.0:
            raise ParameterError("RC 支路电容必须为正数")
        object.__setattr__(self, "resistance_ohm", resistance)
        object.__setattr__(self, "capacitance_f", capacitance)

    @property
    def time_constant_s(self) -> float:
        return self.resistance_ohm * self.capacitance_f


@dataclass(frozen=True)
class CellParameters:
    """单体电池参数。"""

    capacity_ah: float
    r0_ohm: float
    charge_efficiency: float = 1.0
    discharge_efficiency: float = 1.0
    label: str = "cell"
    parameter_source: str = "educational_assumption"
    temperature_c: float = 25.0
    lower_voltage_v: float = 3.0
    upper_voltage_v: float = 4.2

    def __post_init__(self) -> None:
        capacity = _real(self.capacity_ah, "额定容量")
        r0 = _real(self.r0_ohm, "欧姆内阻 R0")
        charge_eff = _real(self.charge_efficiency, "充电库仑效率")
        discharge_eff = _real(self.discharge_efficiency, "放电库仑效率")
        temperature = _real(self.temperature_c, "参考温度")
        lower = _real(self.lower_voltage_v, "参考下限电压")
        upper = _real(self.upper_voltage_v, "参考上限电压")
        if capacity <= 0.0:
            raise ParameterError("额定容量必须为有限正数")
        if r0 < 0.0:
            raise ParameterError("欧姆内阻 R0 允许为零或有限正数")
        if not 0.0 < charge_eff <= 1.0:
            raise ParameterError("充电库仑效率必须位于 (0, 1]")
        if not 0.0 < discharge_eff <= 1.0:
            raise ParameterError("放电库仑效率必须位于 (0, 1]")
        if lower >= upper:
            raise ParameterError("参考上限电压必须大于下限电压")
        if not isinstance(self.label, str) or not self.label:
            raise ParameterError("电芯编号必须是非空字符串")
        if not isinstance(self.parameter_source, str) or not self.parameter_source:
            raise ParameterError("参数来源必须是非空字符串")
        object.__setattr__(self, "capacity_ah", capacity)
        object.__setattr__(self, "r0_ohm", r0)
        object.__setattr__(self, "charge_efficiency", charge_eff)
        object.__setattr__(self, "discharge_efficiency", discharge_eff)
        object.__setattr__(self, "temperature_c", temperature)
        object.__setattr__(self, "lower_voltage_v", lower)
        object.__setattr__(self, "upper_voltage_v", upper)


@dataclass(frozen=True)
class ECMModelDefinition:
    """一个等效电路模型定义：参数 + RC 支路列表。"""

    name: str
    parameters: CellParameters
    branches: tuple[RCBranch, ...] = ()
    parameter_source: str = "educational_assumption"

    def __post_init__(self) -> None:
        if self.name not in ("rint", "first_order_rc", "second_order_rc"):
            raise ParameterError(f"未知模型类型: {self.name!r}")
        if len(self.branches) > 2:
            raise ParameterError("本阶段最多支持两个 RC 支路")
        expected = {"rint": 0, "first_order_rc": 1, "second_order_rc": 2}[self.name]
        if len(self.branches) != expected:
            raise ParameterError(f"{self.name} 需要 {expected} 个 RC 支路，实际 {len(self.branches)}")

    @property
    def order(self) -> int:
        return len(self.branches)

    @property
    def time_constants_s(self) -> tuple[float, ...]:
        return tuple(branch.time_constant_s for branch in self.branches)

    def describe(self) -> dict[str, Any]:
        return {
            "model": self.name,
            "order": self.order,
            "parameter_source": self.parameter_source,
            "capacity_ah": self.parameters.capacity_ah,
            "r0_ohm": self.parameters.r0_ohm,
            "rc_branches": [
                {
                    "resistance_ohm": branch.resistance_ohm,
                    "capacitance_f": branch.capacitance_f,
                    "time_constant_s": branch.time_constant_s,
                }
                for branch in self.branches
            ],
        }


def load_yaml(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    if not target.exists():
        raise ParameterError(f"配置文件不存在: {target}")
    payload = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ParameterError(f"配置文件顶层必须是映射: {target}")
    return dict(payload)


def load_ecm_models(path: str | Path | None = None) -> dict[str, ECMModelDefinition]:
    """读取教学参数配置，构造 Rint / 一阶 RC / 二阶 RC 三个模型定义。"""
    raw = load_yaml(path or CONFIG_DIR / "ecm_parameters.yaml")
    cell = raw["cell"]
    source = str(raw.get("parameter_source", "educational_assumption"))

    def build(prefix: str) -> CellParameters:
        return CellParameters(
            capacity_ah=cell["nominal_capacity_ah"],
            r0_ohm=raw[prefix]["r0_ohm"],
            charge_efficiency=cell.get("charge_coulombic_efficiency", 1.0),
            discharge_efficiency=cell.get("discharge_coulombic_efficiency", 1.0),
            label="cell",
            parameter_source=source,
            temperature_c=cell.get("reference_temperature_c", 25.0),
            lower_voltage_v=cell.get("reference_lower_voltage_v", 3.0),
            upper_voltage_v=cell.get("reference_upper_voltage_v", 4.2),
        )

    first_branches = (
        RCBranch(raw["first_order_rc"]["r1_ohm"], raw["first_order_rc"]["c1_f"]),
    )
    second_branches = (
        RCBranch(raw["second_order_rc"]["r1_ohm"], raw["second_order_rc"]["c1_f"]),
        RCBranch(raw["second_order_rc"]["r2_ohm"], raw["second_order_rc"]["c2_f"]),
    )
    return {
        "rint": ECMModelDefinition("rint", build("rint"), (), source),
        "first_order_rc": ECMModelDefinition(
            "first_order_rc", build("first_order_rc"), first_branches, source
        ),
        "second_order_rc": ECMModelDefinition(
            "second_order_rc", build("second_order_rc"), second_branches, source
        ),
    }


def load_simulation_settings(path: str | Path | None = None) -> dict[str, float]:
    raw = load_yaml(path or CONFIG_DIR / "ecm_parameters.yaml")
    section = raw.get("simulation", {})
    return {
        "output_step_s": _real(section.get("output_step_s", 0.1), "输出时间间隔"),
        "duration_s": _real(section.get("duration_s", 300.0), "仿真时长"),
    }

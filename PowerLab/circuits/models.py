"""基础电路参数模型（全部使用 SI 单位）。

这些 dataclass 只描述电路的物理参数，不构建 PySpice 对象、不执行仿真，
便于配置加载、脚本与测试共享同一套校验规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .validators import (
    ac_sweep,
    dc_sweep,
    finite_number,
    nonnegative_number,
    positive_integer,
    positive_number,
    temperature_celsius,
    transient_parameters,
)


@dataclass(frozen=True)
class VoltageDividerParameters:
    """电阻分压：Vin ─ R1 ─ out ─ R2 ─ GND。"""

    vin_v: float = 12.0
    r1_ohm: float = 1_000.0
    r2_ohm: float = 1_000.0

    def __post_init__(self) -> None:
        finite_number(self.vin_v, "voltage_divider.vin_v")
        positive_number(self.r1_ohm, "voltage_divider.r1_ohm")
        positive_number(self.r2_ohm, "voltage_divider.r2_ohm")

    def to_dict(self) -> dict[str, float]:
        return {"vin_v": self.vin_v, "r1_ohm": self.r1_ohm, "r2_ohm": self.r2_ohm}


@dataclass(frozen=True)
class RCParameters:
    """RC 一阶电路：Vin ─ R ─ out ─ C ─ GND。"""

    input_v: float = 5.0
    resistance_ohm: float = 1_000.0
    capacitance_f: float = 1e-6
    rise_time_s: float = 1e-6

    def __post_init__(self) -> None:
        finite_number(self.input_v, "rc.input_v")
        positive_number(self.resistance_ohm, "rc.resistance_ohm")
        positive_number(self.capacitance_f, "rc.capacitance_f")
        positive_number(self.rise_time_s, "rc.rise_time_s")

    def to_dict(self) -> dict[str, float]:
        return {
            "input_v": self.input_v,
            "resistance_ohm": self.resistance_ohm,
            "capacitance_f": self.capacitance_f,
            "rise_time_s": self.rise_time_s,
        }


@dataclass(frozen=True)
class RLParameters:
    """RL 一阶电路：Vin ─ R ─ 电感节点 ─ L ─ GND。"""

    input_v: float = 5.0
    resistance_ohm: float = 10.0
    inductance_h: float = 0.01
    rise_time_s: float = 1e-6

    def __post_init__(self) -> None:
        finite_number(self.input_v, "rl.input_v")
        positive_number(self.resistance_ohm, "rl.resistance_ohm")
        positive_number(self.inductance_h, "rl.inductance_h")
        positive_number(self.rise_time_s, "rl.rise_time_s")

    def to_dict(self) -> dict[str, float]:
        return {
            "input_v": self.input_v,
            "resistance_ohm": self.resistance_ohm,
            "inductance_h": self.inductance_h,
            "rise_time_s": self.rise_time_s,
        }


@dataclass(frozen=True)
class RLCParameters:
    """串联 RLC：Vin ─ R ─ n1 ─ L ─ out ─ C ─ GND。"""

    input_v: float = 5.0
    resistance_ohm: float = 10.0
    inductance_h: float = 0.01
    capacitance_f: float = 1e-6
    rise_time_s: float = 1e-6

    def __post_init__(self) -> None:
        finite_number(self.input_v, "rlc.input_v")
        positive_number(self.resistance_ohm, "rlc.resistance_ohm")
        positive_number(self.inductance_h, "rlc.inductance_h")
        positive_number(self.capacitance_f, "rlc.capacitance_f")
        positive_number(self.rise_time_s, "rlc.rise_time_s")

    def to_dict(self) -> dict[str, float]:
        return {
            "input_v": self.input_v,
            "resistance_ohm": self.resistance_ohm,
            "inductance_h": self.inductance_h,
            "capacitance_f": self.capacitance_f,
            "rise_time_s": self.rise_time_s,
        }


@dataclass(frozen=True)
class DiodeParameters:
    """教学用 SPICE 二极管模型（非商业器件 Datasheet）。"""

    saturation_current_a: float = 1e-9
    ideality_factor: float = 1.8
    series_resistance_ohm: float = 0.5
    temperature_c: float = 25.0

    def __post_init__(self) -> None:
        positive_number(self.saturation_current_a, "diode.saturation_current_a")
        positive_number(self.ideality_factor, "diode.ideality_factor")
        nonnegative_number(self.series_resistance_ohm, "diode.series_resistance_ohm")
        temperature_celsius(self.temperature_c, "diode.temperature_c")

    def to_dict(self) -> dict[str, float]:
        return {
            "saturation_current_a": self.saturation_current_a,
            "ideality_factor": self.ideality_factor,
            "series_resistance_ohm": self.series_resistance_ohm,
            "temperature_c": self.temperature_c,
        }


@dataclass(frozen=True)
class RectifierParameters:
    """半波整流：正弦源 ─ 源电阻 ─ 二极管 ─ 负载 ─ GND。"""

    input_peak_v: float = 10.0
    frequency_hz: float = 50.0
    source_resistance_ohm: float = 1.0
    load_resistance_ohm: float = 1_000.0
    diode: DiodeParameters = DiodeParameters()

    def __post_init__(self) -> None:
        positive_number(self.input_peak_v, "rectifier.input_peak_v")
        positive_number(self.frequency_hz, "rectifier.frequency_hz")
        positive_number(self.source_resistance_ohm, "rectifier.source_resistance_ohm")
        positive_number(self.load_resistance_ohm, "rectifier.load_resistance_ohm")
        if not isinstance(self.diode, DiodeParameters):
            raise ValueError("rectifier.diode must be DiodeParameters")

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_peak_v": self.input_peak_v,
            "frequency_hz": self.frequency_hz,
            "source_resistance_ohm": self.source_resistance_ohm,
            "load_resistance_ohm": self.load_resistance_ohm,
            "diode": self.diode.to_dict(),
        }


@dataclass(frozen=True)
class TransientParameters:
    """瞬态分析时间参数（秒）。"""

    step_s: float = 1e-5
    end_s: float = 6e-3
    start_s: float = 0.0

    def __post_init__(self) -> None:
        transient_parameters(self.step_s, self.end_s, self.start_s)

    def to_dict(self) -> dict[str, float]:
        return {"step_s": self.step_s, "end_s": self.end_s, "start_s": self.start_s}


@dataclass(frozen=True)
class DcSweepParameters:
    """直流扫描参数（伏特）。"""

    start_v: float = 0.0
    stop_v: float = 12.0
    step_v: float = 0.5

    def __post_init__(self) -> None:
        dc_sweep(self.start_v, self.stop_v, self.step_v)

    def to_dict(self) -> dict[str, float]:
        return {"start_v": self.start_v, "stop_v": self.stop_v, "step_v": self.step_v}


@dataclass(frozen=True)
class AcSweepParameters:
    """交流小信号扫描参数（Hz）。"""

    start_hz: float = 1.0
    stop_hz: float = 100_000.0
    points_per_decade: int = 50
    variation: str = "dec"

    def __post_init__(self) -> None:
        ac_sweep(
            self.start_hz,
            self.stop_hz,
            self.points_per_decade,
            variation=self.variation,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_hz": self.start_hz,
            "stop_hz": self.stop_hz,
            "points_per_decade": self.points_per_decade,
            "variation": self.variation,
        }


@dataclass(frozen=True)
class DampingCase:
    """RLC 阻尼工况：一个电阻值对应一种阻尼状态。"""

    resistance_ohm: float
    label: str

    def __post_init__(self) -> None:
        positive_number(self.resistance_ohm, "damping.resistance_ohm")
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("damping.label must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return {"resistance_ohm": self.resistance_ohm, "label": self.label}


def damping_cases(resistances_ohm: tuple[float, ...]) -> tuple[DampingCase, ...]:
    """把电阻列表转换成带标签的阻尼工况。

    标签只描述"相对临界阻尼的位置"，具体阻尼比由理论模块计算，
    避免在此处硬编码物理结论。
    """
    if not resistances_ohm:
        raise ValueError("damping resistances must not be empty")
    if len(resistances_ohm) != 3:
        raise ValueError("exactly three damping cases are required")
    labels = ("underdamped", "critical", "overdamped")
    return tuple(
        DampingCase(positive_number(value, f"damping.{index}"), label)
        for index, (value, label) in enumerate(zip(resistances_ohm, labels))
    )


def validate_points_per_decade(value: object, name: str = "points_per_decade") -> int:
    """供脚本复用：校验每十倍频程点数。"""
    return positive_integer(value, name, minimum=1)

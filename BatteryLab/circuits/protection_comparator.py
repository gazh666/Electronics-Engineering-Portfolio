"""真实 ngspice 保护比较器：分压、RC 确认延时、迟滞开关。

网表用 ngspice 的电压控制开关 ``S`` 实现带迟滞的比较器（``VT`` 阈值、``VH`` 迟滞），
前端 RC 给出模拟确认延时。测得的跳闸电压、释放电压、迟滞宽度与延时都来自真实
瞬态解，而不是把行为模型结果当作电路结果。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from PySpice.Spice.Netlist import Circuit

from circuits.spice_utils import run_transient, save_netlist
from protection.limits import load_protection_config


class ComparatorSpiceError(RuntimeError):
    """比较器 SPICE 求解失败。"""


@dataclass(frozen=True)
class ComparatorSpiceSettings:
    divider_ratio: float
    overvoltage_spice_threshold_v: float
    overvoltage_spice_hysteresis_v: float
    undervoltage_spice_threshold_v: float
    undervoltage_spice_hysteresis_v: float
    divider_resistance_ohm: float = 10000.0
    delay_resistance_ohm: float = 10000.0
    delay_capacitance_f: float = 10e-6
    pullup_resistance_ohm: float = 10000.0
    supply_voltage_v: float = 3.3

    @property
    def delay_time_constant_s(self) -> float:
        """RC 延时节点时间常数：分压器戴维南电阻 + 延时电阻。"""
        divider = self.divider_resistance_ohm * self.divider_resistance_ohm / (
            2.0 * self.divider_resistance_ohm
        )
        return (self.delay_resistance_ohm + divider) * self.delay_capacitance_f

    def cell_trip_voltage_v(self) -> float:
        return self.overvoltage_spice_threshold_v / self.divider_ratio

    def cell_release_voltage_v(self) -> float:
        return (self.overvoltage_spice_threshold_v - self.overvoltage_spice_hysteresis_v) / self.divider_ratio


def load_comparator_settings(config: Mapping[str, Any] | None = None) -> ComparatorSpiceSettings:
    raw = dict(config) if config is not None else load_protection_config()
    section = raw["comparator"]
    settings = ComparatorSpiceSettings(
        divider_ratio=float(section["divider_ratio"]),
        overvoltage_spice_threshold_v=float(section["overvoltage_spice_threshold_v"]),
        overvoltage_spice_hysteresis_v=float(section["overvoltage_spice_hysteresis_v"]),
        undervoltage_spice_threshold_v=float(section["undervoltage_spice_threshold_v"]),
        undervoltage_spice_hysteresis_v=float(section["undervoltage_spice_hysteresis_v"]),
    )
    if not 0.0 < settings.divider_ratio <= 1.0:
        raise ComparatorSpiceError("分压比必须位于 (0, 1]")
    if settings.overvoltage_spice_hysteresis_v <= 0.0:
        raise ComparatorSpiceError("迟滞必须为正")
    return settings


def build_overvoltage_comparator_circuit(
    settings: ComparatorSpiceSettings,
    input_points: list[tuple[float, float]],
    *,
    step_s: float,
) -> Circuit:
    circuit = Circuit("BatteryLab overvoltage comparator")
    circuit.PieceWiseLinearVoltageSource("CELL", "cell", circuit.gnd, values=input_points)
    # 分压：R1/R2 = 1，得到 divider_ratio = 0.5。
    circuit.R("1", "cell", "mid", settings.divider_resistance_ohm)
    circuit.R("2", "mid", circuit.gnd, settings.divider_resistance_ohm)
    circuit.R("3", "mid", "nin", settings.delay_resistance_ohm)
    circuit.C("1", "nin", circuit.gnd, settings.delay_capacitance_f)
    circuit.V("DD", "vdd", circuit.gnd, settings.supply_voltage_v)
    circuit.S(
        "1",
        "out",
        "vdd",
        "nin",
        circuit.gnd,
        model="CMP_SW",
    )
    circuit.model(
        "CMP_SW",
        "SW",
        # 阶梯实测（见 docs/46）：ngspice S 模型在控制节点 VT+VH 处导通、
        # VT−VH 处关断。令 width 为期望的控制节点迟滞宽度，
        # 则 VH = width/2，VT = 阈值 − width/2，实测跳闸点等于配置阈值。
        VT=settings.overvoltage_spice_threshold_v - settings.overvoltage_spice_hysteresis_v / 2.0,
        VH=settings.overvoltage_spice_hysteresis_v / 2.0,
        RON=100.0,
        ROFF=1e9,
    )
    circuit.R("PD", "out", circuit.gnd, settings.pullup_resistance_ohm)
    return circuit


@dataclass(frozen=True)
class ComparatorSpiceResult:
    cell_trip_voltage_v: float
    cell_release_voltage_v: float
    measured_trip_voltage_v: float | None
    measured_release_voltage_v: float | None
    measured_hysteresis_v: float | None
    configured_hysteresis_v: float
    measured_delay_s: float | None
    analytic_delay_s: float
    delay_relative_error: float | None
    waveform: dict[str, np.ndarray]
    netlist: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_trip_voltage_v": self.cell_trip_voltage_v,
            "cell_release_voltage_v": self.cell_release_voltage_v,
            "measured_trip_voltage_v": self.measured_trip_voltage_v,
            "measured_release_voltage_v": self.measured_release_voltage_v,
            "measured_hysteresis_v": self.measured_hysteresis_v,
            "configured_hysteresis_v": self.configured_hysteresis_v,
            "measured_delay_s": self.measured_delay_s,
            "analytic_delay_s": self.analytic_delay_s,
            "delay_relative_error": self.delay_relative_error,
        }


def run_overvoltage_comparator_spice(
    settings: ComparatorSpiceSettings | None = None,
) -> ComparatorSpiceResult:
    """三角波扫描：测得跳闸/释放阈值与迟滞，再单独做阶跃测延时。"""
    config = settings or load_comparator_settings()
    trip_cell = config.cell_trip_voltage_v()
    low = trip_cell - 0.25
    high = trip_cell + 0.25
    period = 0.8
    points = [
        (0.0, low),
        (period, high),
        (2.0 * period, low),
    ]
    circuit = build_overvoltage_comparator_circuit(config, points, step_s=5e-4)
    data = run_transient(
        circuit,
        duration_s=2.0 * period,
        step_s=5e-4,
        max_step_s=5e-4,
        nodes=("cell", "nin", "out"),
        reltol=1e-5,
        abstol=1e-9,
        vntol=1e-6,
    )
    time_array = data["time_s"]
    cell = data["cell"]
    filtered = data["nin"]
    out = data["out"]
    threshold = 0.5 * config.supply_voltage_v
    rising = np.where((out[:-1] < threshold) & (out[1:] >= threshold))[0]
    falling = np.where((out[:-1] >= threshold) & (out[1:] < threshold))[0]
    # 判决发生在滤波节点 nin；折算回单体端电压需要除以分压比。
    measured_trip = (
        float(filtered[rising[0] + 1]) / config.divider_ratio if rising.size else None
    )
    measured_release = (
        float(filtered[falling[0] + 1]) / config.divider_ratio if falling.size else None
    )
    hysteresis = (
        None if measured_trip is None or measured_release is None else measured_trip - measured_release
    )

    # 阶跃延时：从阈值下方 50 mV（控制节点）跳到阈值上方 100 mV。
    start_cell = (config.overvoltage_spice_threshold_v - 0.05) / config.divider_ratio
    target_cell = (config.overvoltage_spice_threshold_v + 0.10) / config.divider_ratio
    step_points = [
        (0.0, start_cell),
        (0.02, start_cell),
        (0.020001, target_cell),
        (0.60, target_cell),
    ]
    step_circuit = build_overvoltage_comparator_circuit(config, step_points, step_s=1e-4)
    step_data = run_transient(
        step_circuit,
        duration_s=0.60,
        step_s=1e-4,
        max_step_s=1e-4,
        nodes=("cell", "nin", "out"),
        reltol=1e-5,
        abstol=1e-9,
        vntol=1e-6,
    )
    step_time = step_data["time_s"]
    step_out = step_data["out"]
    above = np.where(step_out >= threshold)[0]
    measured_delay = float(step_time[above[0]] - step_time[0] - 0.02) if above.size else None

    # 解析延时：RC 从起始电压充电到阈值。
    v0 = start_cell * config.divider_ratio
    vf = target_cell * config.divider_ratio
    vt = config.overvoltage_spice_threshold_v
    ratio = (vf - vt) / (vf - v0) if vf != v0 else 0.0
    analytic_delay = (
        -config.delay_time_constant_s * math.log(ratio) if 0.0 < ratio < 1.0 else float("inf")
    )
    relative = (
        None
        if measured_delay is None or not math.isfinite(analytic_delay) or analytic_delay == 0.0
        else abs(measured_delay - analytic_delay) / analytic_delay
    )

    waveform = {
        "time_s": time_array,
        "cell_voltage_v": cell,
        "comparator_output_v": out,
        "step_time_s": step_time,
        "step_cell_voltage_v": step_data["cell"],
        "step_filtered_voltage_v": step_data["nin"],
        "step_comparator_output_v": step_out,
    }
    return ComparatorSpiceResult(
        cell_trip_voltage_v=trip_cell,
        cell_release_voltage_v=config.cell_release_voltage_v(),
        measured_trip_voltage_v=measured_trip,
        measured_release_voltage_v=measured_release,
        measured_hysteresis_v=hysteresis,
        configured_hysteresis_v=config.overvoltage_spice_hysteresis_v / config.divider_ratio,
        measured_delay_s=measured_delay,
        analytic_delay_s=analytic_delay,
        delay_relative_error=relative,
        waveform=waveform,
        netlist=str(circuit),
    )


def save_comparator_netlist(settings: ComparatorSpiceSettings, path) -> Any:
    points = [(0.0, settings.cell_release_voltage_v()), (1.0, settings.cell_trip_voltage_v() + 0.2)]
    return save_netlist(build_overvoltage_comparator_circuit(settings, points, step_s=1e-4), path)

"""Buck 真实波形提取与 PWM 波形分析。

波形字段全部来自 ngspice 输出的节点 / 支路，或由这些真实波形按明确公式派生：

- ``input_current_a = -I(VIN)``：SPICE 电压源支路电流以流入源内部为正。
- ``load_current_a = Vout / Rload``：恒阻负载派生量。
- ``capacitor_current_a = IL - Iload``：KCL 派生量。
- ``inductor_voltage_v = V(lx) - V(out)``。

PWM 分析只使用真实 gate 波形，通过阈值线性插值提取边沿，
不把配置占空比直接当成实测占空比。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from circuits.buck import (
    BRANCH_INPUT,
    BRANCH_SENSE,
    NODE_GATE,
    NODE_INDUCTOR,
    NODE_OUTPUT,
    NODE_SWITCH,
    NODE_VIN,
)
from circuits.validators import finite_number, positive_number

NONIDEAL_WAVEFORM_COLUMNS = (
    "time_s",
    "vin_v",
    "drive_vgs_command_v",
    "gate_to_ground_v",
    "mosfet_vgs_v",
    "mosfet_vds_v",
    "mosfet_drain_terminal_current_a",
    "gate_current_a",
    "switch_node_v",
    "diode_anode_cathode_voltage_v",
    "diode_current_a",
    "inductor_voltage_v",
    "inductor_current_a",
    "inductor_dcr_voltage_v",
    "capacitor_internal_voltage_v",
    "capacitor_current_a",
    "capacitor_esr_voltage_v",
    "vout_v",
    "load_current_a",
    "input_current_a",
    "driver_current_a",
)

WAVEFORM_COLUMNS = (
    "time_s",
    "vin_v",
    "gate_v",
    "switch_node_v",
    "inductor_voltage_v",
    "vout_v",
    "input_current_a",
    "inductor_current_a",
    "load_current_a",
    "capacitor_current_a",
)


def _series(values: Any, name: str) -> np.ndarray:
    array = np.array(values, dtype=float, copy=True)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a non-empty 1D waveform")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains NaN or Infinity")
    return array


def _node(analysis: Any, name: str) -> np.ndarray:
    nodes = getattr(analysis, "nodes", None)
    if not isinstance(nodes, Mapping) or name not in nodes:
        available = ", ".join(sorted(str(key) for key in (nodes or {}))) or "<none>"
        raise ValueError(f"node {name!r} not found; available: {available}")
    return _series(nodes[name], f"V({name})")


def _branch(analysis: Any, candidates: tuple[str, ...]) -> tuple[str, np.ndarray]:
    branches = getattr(analysis, "branches", None)
    if not isinstance(branches, Mapping) or not branches:
        raise ValueError("analysis contains no branch currents")
    for name in candidates:
        if name in branches:
            return name, _series(branches[name], f"I({name})")
    available = ", ".join(sorted(str(key) for key in branches)) or "<none>"
    raise ValueError(
        f"branch not found for {candidates}; available: {available}"
    )


def _assemble(
    time_s: np.ndarray,
    vin: np.ndarray,
    gate: np.ndarray,
    vsw: np.ndarray,
    lx: np.ndarray,
    vout: np.ndarray,
    input_current: np.ndarray,
    inductor_current: np.ndarray,
    load_resistance_ohm: float,
) -> pd.DataFrame:
    load_resistance = positive_number(load_resistance_ohm, "load_resistance_ohm")
    for name, array in (
        ("time_s", time_s),
        ("vin", vin),
        ("gate", gate),
        ("switch_node", vsw),
        ("lx", lx),
        ("vout", vout),
        ("input_current", input_current),
        ("inductor_current", inductor_current),
    ):
        if array.shape != time_s.shape:
            raise ValueError(f"{name} length mismatch with time axis")
    if time_s.size < 2:
        raise ValueError("time axis needs at least two samples")
    if not np.all(np.diff(time_s) > 0):
        raise ValueError("time axis must be strictly increasing")

    load_current = vout / load_resistance
    capacitor_current = inductor_current - load_current
    return pd.DataFrame(
        {
            "time_s": time_s,
            "vin_v": vin,
            "gate_v": gate,
            "switch_node_v": vsw,
            "inductor_voltage_v": lx - vout,
            "vout_v": vout,
            "input_current_a": input_current,
            "inductor_current_a": inductor_current,
            "load_current_a": load_current,
            "capacitor_current_a": capacitor_current,
        }
    )


def extract_buck_waveforms(analysis: Any, load_resistance_ohm: float) -> pd.DataFrame:
    """从 PySpice 瞬态分析对象提取标准 Buck 波形。"""
    time_s = _series(getattr(analysis, "time", None), "time")
    vin = _node(analysis, NODE_VIN)
    gate = _node(analysis, NODE_GATE)
    vsw = _node(analysis, NODE_SWITCH)
    lx = _node(analysis, NODE_INDUCTOR)
    vout = _node(analysis, NODE_OUTPUT)

    _, input_source_current = _branch(analysis, (BRANCH_INPUT, "vvin"))
    _, inductor_current = _branch(analysis, (BRANCH_SENSE, "l1"))

    return _assemble(
        time_s,
        vin,
        gate,
        vsw,
        lx,
        vout,
        -input_source_current,
        inductor_current,
        load_resistance_ohm,
    )


def buck_waveforms_from_result(
    data: pd.DataFrame,
    load_resistance_ohm: float,
) -> pd.DataFrame:
    """把 :class:`SimulationResult` 的通用列名转换为标准 Buck 波形。

    要求列名来自 :meth:`SimulationRunner.run_transient`：
    ``vin_v`` / ``gate_v`` / ``sw_v`` / ``lx_v`` / ``out_v`` /
    ``vin_branch_current_a`` / ``vsense_branch_current_a``。
    """
    if not isinstance(data, pd.DataFrame):
        raise ValueError("data must be a pandas.DataFrame")
    required = ("time_s", "vin_v", "gate_v", "sw_v", "lx_v", "out_v", "vin_branch_current_a")
    missing = [name for name in required if name not in data.columns]
    if missing:
        raise ValueError(f"missing required transient columns: {missing}")

    inductor_column = next(
        (
            name
            for name in ("vsense_branch_current_a", "l1_branch_current_a")
            if name in data.columns
        ),
        None,
    )
    if inductor_column is None:
        raise ValueError(
            "inductor current column not found; expected vsense_branch_current_a or l1_branch_current_a"
        )

    time_s = _series(data["time_s"], "time_s")
    return _assemble(
        time_s,
        _series(data["vin_v"], "vin_v"),
        _series(data["gate_v"], "gate_v"),
        _series(data["sw_v"], "sw_v"),
        _series(data["lx_v"], "lx_v"),
        _series(data["out_v"], "out_v"),
        -_series(data["vin_branch_current_a"], "vin_branch_current_a"),
        _series(data[inductor_column], inductor_column),
        load_resistance_ohm,
    )


def threshold_crossing_time(
    t0: float,
    t1: float,
    y0: float,
    y1: float,
    threshold: float,
) -> float:
    """用相邻采样点线性插值求阈值交点时间。"""
    t0 = finite_number(t0, "t0")
    t1 = finite_number(t1, "t1")
    y0 = finite_number(y0, "y0")
    y1 = finite_number(y1, "y1")
    threshold = finite_number(threshold, "threshold")
    if t1 <= t0:
        raise ValueError("t1 must be greater than t0")
    if y1 == y0:
        raise ValueError("cannot interpolate a threshold crossing on a flat segment")
    ratio = (threshold - y0) / (y1 - y0)
    return t0 + ratio * (t1 - t0)


@dataclass(frozen=True)
class PWMAnalysis:
    """真实 gate 波形的周期与占空比统计。"""

    threshold_v: float
    rising_edge_times_s: tuple[float, ...]
    falling_edge_times_s: tuple[float, ...]
    cycle_start_times_s: tuple[float, ...]
    cycle_end_times_s: tuple[float, ...]
    cycle_periods_s: tuple[float, ...]
    cycle_duties: tuple[float, ...]
    cycle_pulse_widths_s: tuple[float, ...]
    mean_frequency_hz: float
    frequency_std_hz: float
    mean_duty_cycle: float
    duty_std: float
    complete_cycles: int
    data_source: str = "spice_simulation"

    @property
    def cycle_boundaries_s(self) -> tuple[float, ...]:
        """完整周期边界（首周期起点 + 末周期终点）。"""
        if not self.cycle_start_times_s:
            return ()
        return self.cycle_start_times_s + (self.cycle_end_times_s[-1],)

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold_v": self.threshold_v,
            "rising_edge_count": len(self.rising_edge_times_s),
            "falling_edge_count": len(self.falling_edge_times_s),
            "complete_cycles": self.complete_cycles,
            "first_rising_edge_s": (
                self.rising_edge_times_s[0] if self.rising_edge_times_s else None
            ),
            "last_rising_edge_s": (
                self.rising_edge_times_s[-1] if self.rising_edge_times_s else None
            ),
            "mean_period_s": (
                float(np.mean(self.cycle_periods_s)) if self.cycle_periods_s else None
            ),
            "cycle_period_s": list(self.cycle_periods_s),
            "mean_frequency_hz": self.mean_frequency_hz,
            "frequency_std_hz": self.frequency_std_hz,
            "mean_duty_cycle": self.mean_duty_cycle,
            "duty_std": self.duty_std,
            "cycle_duty_cycle": list(self.cycle_duties),
            "mean_pulse_width_s": (
                float(np.mean(self.cycle_pulse_widths_s)) if self.cycle_pulse_widths_s else None
            ),
            "data_source": self.data_source,
        }


def threshold_crossings(
    time_s: Any,
    values: Any,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    """返回上升沿与下降沿的阈值交点时间（秒）。"""
    time = _series(time_s, "time_s")
    wave = _series(values, "values")
    if time.shape != wave.shape:
        raise ValueError("time and values must have the same length")
    if not np.all(np.diff(time) > 0):
        raise ValueError("time axis must be strictly increasing")
    level = finite_number(threshold, "threshold")

    relative = wave - level
    rising: list[float] = []
    falling: list[float] = []
    for index in range(len(time) - 1):
        y0 = float(relative[index])
        y1 = float(relative[index + 1])
        if y0 < 0.0 <= y1 or y0 == 0.0 < y1:
            crossing = threshold_crossing_time(
                float(time[index]), float(time[index + 1]),
                float(wave[index]), float(wave[index + 1]), level,
            )
            rising.append(crossing)
        elif y0 > 0.0 >= y1 or y0 == 0.0 > y1:
            crossing = threshold_crossing_time(
                float(time[index]), float(time[index + 1]),
                float(wave[index]), float(wave[index + 1]), level,
            )
            falling.append(crossing)
    return np.asarray(rising, dtype=float), np.asarray(falling, dtype=float)


def analyze_pwm_waveform(
    time_s: Any,
    gate_voltage_v: Any,
    *,
    low_voltage_v: float,
    high_voltage_v: float,
) -> PWMAnalysis:
    """从真实 gate 波形提取周期、占空比与脉冲宽度。

    只统计完整的「上升沿 → 下降沿 → 下一个上升沿」周期，
    自动忽略仿真开始前 / 记录结束后的不完整脉冲。
    """
    low = finite_number(low_voltage_v, "low_voltage_v")
    high = finite_number(high_voltage_v, "high_voltage_v")
    if high <= low:
        raise ValueError("high_voltage_v must exceed low_voltage_v")

    time = _series(time_s, "time_s")
    gate = _series(gate_voltage_v, "gate_voltage_v")
    if time.shape != gate.shape:
        raise ValueError("time and gate voltage must have the same length")

    threshold = 0.5 * (low + high)
    rising, falling = threshold_crossings(time, gate, threshold)
    if rising.size < 2:
        raise ValueError("at least two rising edges are required to measure a PWM cycle")

    period_list: list[float] = []
    duty_list: list[float] = []
    pulse_list: list[float] = []
    starts: list[float] = []
    ends: list[float] = []

    falling_index = 0
    for index in range(rising.size - 1):
        start = float(rising[index])
        end = float(rising[index + 1])
        while falling_index < falling.size and falling[falling_index] <= start:
            falling_index += 1
        if falling_index >= falling.size:
            break
        stop = float(falling[falling_index])
        if stop >= end:
            continue
        period = end - start
        pulse = stop - start
        if period <= 0.0 or pulse <= 0.0:
            continue
        period_list.append(period)
        pulse_list.append(pulse)
        duty_list.append(pulse / period)
        starts.append(start)
        ends.append(end)
        falling_index += 1

    if not period_list:
        raise ValueError("no complete PWM cycle was found in the recorded waveform")

    periods = np.asarray(period_list, dtype=float)
    duties = np.asarray(duty_list, dtype=float)
    frequencies = 1.0 / periods

    return PWMAnalysis(
        threshold_v=threshold,
        rising_edge_times_s=tuple(float(value) for value in rising),
        falling_edge_times_s=tuple(float(value) for value in falling),
        cycle_start_times_s=tuple(starts),
        cycle_end_times_s=tuple(ends),
        cycle_periods_s=tuple(period_list),
        cycle_duties=tuple(duty_list),
        cycle_pulse_widths_s=tuple(pulse_list),
        mean_frequency_hz=float(1.0 / np.mean(periods)),
        frequency_std_hz=float(np.std(frequencies)),
        mean_duty_cycle=float(np.mean(duties)),
        duty_std=float(np.std(duties)),
        complete_cycles=len(period_list),
    )


def _column(data: pd.DataFrame, name: str, *, required: bool = True) -> np.ndarray | None:
    if name in data.columns:
        return _series(data[name], name)
    if required:
        raise ValueError(f"missing required transient column: {name}")
    return None


def extract_nonideal_waveforms(
    data: pd.DataFrame,
    *,
    load_resistance_ohm: float,
    gate_resistance_ohm: float | None = None,
    pulldown_resistance_ohm: float | None = None,
) -> pd.DataFrame:
    """从真实瞬态结果提取非理想 Buck 统一波形字段。

    统一字段全部来自 ngspice 节点 / 支路，或由这些真实波形按明确公式派生：

    - ``mosfet_drain_terminal_current_a = i(VDSENSE)``
    - ``inductor_current_a = i(VLSENSE)``
    - ``capacitor_current_a = i(VCSENSE)``，同时应满足 ``IL - Iload``
    - ``diode_current_a = i(VDIOSENSE)``
    - ``gate_current_a = (V(drv)-V(gate))/RG - V(gate,sw)/RGS``
    - ``driver_current_a = -i(VDRV)``

    对第三阶段遗留的 Model A（无 DCR/ESR/驱动节点）使用等效派生：
    ``driver_current_a = gate_current_a = -i(VPWM)``，``ESR/DCR 电压 = 0``。
    """
    if not isinstance(data, pd.DataFrame):
        raise ValueError("data must be a pandas.DataFrame")
    load_resistance = positive_number(load_resistance_ohm, "load_resistance_ohm")

    time_s = _column(data, "time_s")
    vin = _column(data, "vin_v")
    vsw = _column(data, "sw_v")
    vout = _column(data, "out_v")
    gate = _column(data, "gate_v")

    unified = "vdsense_branch_current_a" in data.columns
    if unified:
        inductor_column = "vlsense_branch_current_a"
        capacitor_column = "vcsense_branch_current_a"
        diode_column = "vdiosense_branch_current_a"
        lx = _column(data, "lx_v")
        l_dcr = _column(data, "l_dcr_v", required=False)
        cap_internal = _column(data, "cap_internal_v", required=False)
        c_esr = _column(data, "c_esr_v", required=False)
        # 零 DCR / 零 ESR 时对应内部节点不存在，电压降按 0 处理。
        if l_dcr is None:
            l_dcr = vout
        if cap_internal is None:
            cap_internal = vout
        if c_esr is None:
            c_esr = cap_internal
        diode_anode = _column(data, "diode_a_v")
        drain = _column(data, "drain_v")
        drive = _column(data, "drv_v", required=False)
        inductor_current = _column(data, inductor_column)
        capacitor_current = _column(data, capacitor_column)
        diode_current = _column(data, diode_column)
        drain_current = _column(data, "vdsense_branch_current_a")
        input_current = -_column(data, "vin_branch_current_a")
    else:
        inductor_current = _column(data, "vsense_branch_current_a")
        input_current = -_column(data, "vin_branch_current_a")
        lx = _column(data, "lx_v")
        l_dcr = vout
        cap_internal = vout
        c_esr = vout
        diode_anode = np.zeros_like(vout)
        drain = vin
        drive = None
        capacitor_current = None
        diode_current = None
        drain_current = input_current

    load_current = vout / load_resistance
    if capacitor_current is None:
        capacitor_current = inductor_current - load_current
    if diode_current is None:
        diode_current = inductor_current - input_current

    if drive is not None:
        if gate_resistance_ohm is None or pulldown_resistance_ohm is None:
            raise ValueError(
                "gate_resistance_ohm and pulldown_resistance_ohm are required for floating driver results"
            )
        rg = positive_number(gate_resistance_ohm, "gate_resistance_ohm")
        rgs = positive_number(pulldown_resistance_ohm, "pulldown_resistance_ohm")
        driver_current = (_column(data, "vdrv_branch_current_a")) * -1.0
        gate_resistor_current = (drive - gate) / rg
        pulldown_current = (gate - vsw) / rgs
        gate_current = gate_resistor_current - pulldown_current
        drive_command = drive - vsw
    else:
        drive_command = gate
        if "vpwm_branch_current_a" in data.columns:
            gate_current = -_column(data, "vpwm_branch_current_a")
        else:
            gate_current = np.zeros_like(gate)
        driver_current = gate_current

    frame = pd.DataFrame(
        {
            "time_s": time_s,
            "vin_v": vin,
            "drive_vgs_command_v": drive_command,
            "gate_to_ground_v": gate,
            "mosfet_vgs_v": gate - vsw,
            "mosfet_vds_v": drain - vsw,
            "mosfet_drain_terminal_current_a": drain_current,
            "gate_current_a": gate_current,
            "switch_node_v": vsw,
            "diode_anode_cathode_voltage_v": diode_anode - vsw,
            "diode_current_a": diode_current,
            "inductor_voltage_v": lx - l_dcr,
            "inductor_current_a": inductor_current,
            "inductor_dcr_voltage_v": l_dcr - vout,
            "capacitor_internal_voltage_v": cap_internal,
            "capacitor_current_a": capacitor_current,
            "capacitor_esr_voltage_v": c_esr - cap_internal,
            "vout_v": vout,
            "load_current_a": load_current,
            "input_current_a": input_current,
            "driver_current_a": driver_current,
        }
    )
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("extracted nonideal waveforms contain NaN or Infinity")
    return frame

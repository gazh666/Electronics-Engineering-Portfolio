"""损耗分解与开关过渡能量。

本模块只做「由真实波形计算损耗」的公式，不判断合格性。

损耗边界（互不重叠）：

- ``mosfet_network``：漏极端口功率 ``<VDS*ID>`` + 栅极端口功率 ``<VGS*IG>``
- ``diode``：``<V_AK * I_D>``
- ``dcr``：``Irms(IL)^2 * DCR``
- ``esr``：``Irms(IC)^2 * ESR``
- ``gate_resistor``：``Irms(IRG)^2 * RG``
- ``pulldown``：``<VGS^2 / RGS>``

其中 ``IG`` 是流入 MOSFET 栅极终端的电流，不含下拉电阻；
``IRG`` 是流过栅极串联电阻的电流。两者之差即下拉支路电流。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from circuits.validators import finite_number, nonnegative_number, positive_number

from .power_metrics import average_power, rms_value, time_average


def _waveforms(time_s: Any, *arrays: Any) -> tuple[np.ndarray, ...]:
    time = np.array(time_s, dtype=float, copy=True)
    if time.ndim != 1 or time.size < 2:
        raise ValueError("time_s must be a 1D array with at least two samples")
    if not np.all(np.diff(time) > 0):
        raise ValueError("time_s must be strictly increasing")
    result = [time]
    for index, values in enumerate(arrays):
        array = np.array(values, dtype=float, copy=True)
        if array.shape != time.shape:
            raise ValueError(f"waveform {index} does not match the time axis")
        if not np.isfinite(array).all():
            raise ValueError(f"waveform {index} contains NaN or Infinity")
        result.append(array)
    return tuple(result)


def resistor_loss(time_s: Any, current_a: Any, resistance_ohm: float) -> float:
    """电阻损耗 ``Irms^2 * R``。"""
    resistance = nonnegative_number(resistance_ohm, "resistance_ohm")
    if resistance == 0:
        return 0.0
    return rms_value(time_s, current_a) ** 2 * resistance


def inductor_dcr_loss(time_s: Any, inductor_current_a: Any, dcr_ohm: float) -> float:
    """电感绕组 DCR 损耗。"""
    return resistor_loss(time_s, inductor_current_a, dcr_ohm)


def capacitor_esr_loss(time_s: Any, capacitor_current_a: Any, esr_ohm: float) -> float:
    """电容 ESR 损耗。"""
    return resistor_loss(time_s, capacitor_current_a, esr_ohm)


def diode_loss(time_s: Any, diode_voltage_v: Any, diode_current_a: Any) -> float:
    """二极管瞬时功率平均，不做正负截断。"""
    return average_power(time_s, diode_voltage_v, diode_current_a)


def mosfet_network_loss(
    time_s: Any,
    drain_source_voltage_v: Any,
    drain_current_a: Any,
    gate_source_voltage_v: Any,
    gate_terminal_current_a: Any,
) -> float:
    """MOSFET 网络平均损耗 = 漏极端口 + 栅极端口。"""
    drain = average_power(time_s, drain_source_voltage_v, drain_current_a)
    gate = average_power(time_s, gate_source_voltage_v, gate_terminal_current_a)
    return float(drain + gate)


def gate_network_losses(
    time_s: Any,
    *,
    drive_voltage_v: Any,
    gate_voltage_v: Any,
    gate_current_a: Any,
    gate_resistance_ohm: float,
    pulldown_resistance_ohm: float,
    driver_current_a: Any | None = None,
) -> dict[str, float]:
    """栅极电阻、下拉电阻与驱动输入功率。

    ``drive_voltage_v`` 与 ``gate_voltage_v`` 都必须以源极（开关节点）为参考，
    差值才是栅极串联电阻两端电压。
    """
    rg = nonnegative_number(gate_resistance_ohm, "gate_resistance_ohm")
    rgs = nonnegative_number(pulldown_resistance_ohm, "pulldown_resistance_ohm")
    time, drive, gate, gate_current = _waveforms(
        time_s, drive_voltage_v, gate_voltage_v, gate_current_a
    )

    if rg > 0:
        resistor_current = (drive - gate) / rg
        resistor_current_rms = rms_value(time, resistor_current)
        gate_resistor_loss = resistor_current_rms ** 2 * rg
    else:
        gate_resistor_loss = 0.0
        resistor_current_rms = 0.0

    if rgs > 0:
        pulldown_current_rms = rms_value(time, gate / rgs)
        pulldown_loss = rms_value(time, gate) ** 2 / rgs
    else:
        pulldown_loss = 0.0
        pulldown_current_rms = 0.0

    if driver_current_a is None:
        driver_power = 0.0
        driver_current_rms = 0.0
    else:
        driver_current = np.array(driver_current_a, dtype=float, copy=True)
        if driver_current.shape != time.shape:
            raise ValueError("driver_current_a does not match the time axis")
        driver_power = average_power(time, drive, driver_current)
        driver_current_rms = rms_value(time, driver_current)

    return {
        "gate_resistor_loss_w": gate_resistor_loss,
        "pulldown_loss_w": pulldown_loss,
        "driver_input_power_w": driver_power,
        "gate_resistor_current_rms_a": resistor_current_rms,
        "pulldown_current_rms_a": pulldown_current_rms,
        "driver_current_rms_a": driver_current_rms,
        "gate_terminal_current_rms_a": rms_value(time, gate_current),
    }


def _crossing_time(t0: float, t1: float, y0: float, y1: float, level: float) -> float:
    if y1 == y0:
        return float(t0)
    return float(t0 + (level - y0) / (y1 - y0) * (t1 - t0))


def threshold_intervals(
    time_s: Any,
    values: Any,
    *,
    low_level: float,
    high_level: float,
    rising: bool,
) -> list[tuple[float, float]]:
    """返回在 ``low_level`` 与 ``high_level`` 之间跨越的过渡区间。

    ``rising=True`` 表示从低到高（10% → 90%），``False`` 表示从高到低。
    """
    time, wave = _waveforms(time_s, values)
    low = finite_number(low_level, "low_level")
    high = finite_number(high_level, "high_level")
    if high <= low:
        raise ValueError("high_level must exceed low_level")

    intervals: list[tuple[float, float]] = []
    armed = False
    start_time: float | None = None
    for index in range(len(time) - 1):
        y0 = float(wave[index])
        y1 = float(wave[index + 1])
        if rising:
            if not armed and y0 < low <= y1:
                start_time = _crossing_time(
                    float(time[index]), float(time[index + 1]), y0, y1, low
                )
                armed = True
            elif armed and y0 < high <= y1 and start_time is not None:
                end_time = _crossing_time(
                    float(time[index]), float(time[index + 1]), y0, y1, high
                )
                if end_time > start_time:
                    intervals.append((start_time, end_time))
                armed = False
                start_time = None
        else:
            if not armed and y1 < high <= y0:
                start_time = _crossing_time(
                    float(time[index]), float(time[index + 1]), y0, y1, high
                )
                armed = True
            elif armed and y1 < low <= y0 and start_time is not None:
                end_time = _crossing_time(
                    float(time[index]), float(time[index + 1]), y0, y1, low
                )
                if end_time > start_time:
                    intervals.append((start_time, end_time))
                armed = False
                start_time = None
    return intervals


def interval_energy(
    time_s: Any,
    voltage_v: Any,
    current_a: Any,
    interval: tuple[float, float],
) -> float:
    """在指定时间区间内积分 ``v(t)*i(t)``，返回焦耳。"""
    time, voltage, current = _waveforms(time_s, voltage_v, current_a)
    start, end = interval
    if end <= start:
        raise ValueError("interval end must exceed its start")
    mask = (time >= start) & (time <= end)
    if int(mask.sum()) < 2:
        return 0.0
    selected_time = time[mask]
    selected = voltage[mask] * current[mask]
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(selected, selected_time))
    return float(np.trapz(selected, selected_time))  # pragma: no cover


@dataclass(frozen=True)
class SwitchingEnergy:
    """一次窗口内的开关过渡能量统计。"""

    turn_on_intervals_s: tuple[tuple[float, float], ...]
    turn_off_intervals_s: tuple[tuple[float, float], ...]
    turn_on_energy_j: float
    turn_off_energy_j: float
    total_energy_j: float
    measurement_note: str
    data_source: str = "spice_simulation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_on_intervals_s": [list(item) for item in self.turn_on_intervals_s],
            "turn_off_intervals_s": [list(item) for item in self.turn_off_intervals_s],
            "turn_on_count": len(self.turn_on_intervals_s),
            "turn_off_count": len(self.turn_off_intervals_s),
            "turn_on_energy_j": self.turn_on_energy_j,
            "turn_off_energy_j": self.turn_off_energy_j,
            "total_energy_j": self.total_energy_j,
            "measurement_note": self.measurement_note,
            "data_source": self.data_source,
        }


def switching_energy(
    time_s: Any,
    drain_source_voltage_v: Any,
    drain_current_a: Any,
    gate_source_voltage_v: Any,
    *,
    low_level_v: float,
    high_level_v: float,
) -> SwitchingEnergy:
    """在栅极 10%–90% 过渡区间积分 ``VDS*ID``。"""
    time, vds, drain, gate = _waveforms(
        time_s, drain_source_voltage_v, drain_current_a, gate_source_voltage_v
    )
    span = float(high_level_v) - float(low_level_v)
    if span <= 0:
        raise ValueError("high_level_v must exceed low_level_v")
    low = float(low_level_v) + 0.1 * span
    high = float(low_level_v) + 0.9 * span

    turn_on = threshold_intervals(
        time, gate, low_level=low, high_level=high, rising=True
    )
    turn_off = threshold_intervals(
        time, gate, low_level=low, high_level=high, rising=False
    )
    e_on = sum(interval_energy(time, vds, drain, interval) for interval in turn_on)
    e_off = sum(interval_energy(time, vds, drain, interval) for interval in turn_off)
    note = (
        "energy is integrated only inside detected 10%-90% gate transitions; "
        "with coarse output sampling the transition may span few points, "
        "so use the time-step comparison before trusting this value"
    )
    return SwitchingEnergy(
        turn_on_intervals_s=tuple(turn_on),
        turn_off_intervals_s=tuple(turn_off),
        turn_on_energy_j=float(e_on),
        turn_off_energy_j=float(e_off),
        total_energy_j=float(e_on + e_off),
        measurement_note=note,
    )


def gate_on_intervals(
    time_s: Any,
    gate_source_voltage_v: Any,
    *,
    threshold_v: float,
) -> list[tuple[float, float]]:
    """返回 ``VGS`` 高于阈值的导通区间。"""
    time, gate = _waveforms(time_s, gate_source_voltage_v)
    level = finite_number(threshold_v, "threshold_v")
    above = gate > level
    intervals: list[tuple[float, float]] = []
    start: float | None = None
    for index in range(len(time)):
        if above[index] and start is None:
            start = float(time[index])
        elif not above[index] and start is not None:
            intervals.append((start, float(time[index])))
            start = None
    if start is not None:
        intervals.append((start, float(time[-1])))
    return intervals


def conduction_loss_in_on_windows(
    time_s: Any,
    drain_current_a: Any,
    gate_source_voltage_v: Any,
    *,
    rds_on_ohm: float,
    gate_threshold_v: float,
) -> float:
    """在真实导通区间内积分 ``ID^2 * RDS(on)`` 并对整个窗口取平均。"""
    time, current, gate = _waveforms(time_s, drain_current_a, gate_source_voltage_v)
    resistance = positive_number(rds_on_ohm, "rds_on_ohm")
    duration = float(time[-1] - time[0])
    if duration <= 0:
        raise ValueError("time window must have positive duration")

    total = 0.0
    for start, end in gate_on_intervals(time, gate, threshold_v=gate_threshold_v):
        mask = (time >= start) & (time <= end)
        if int(mask.sum()) < 2:
            continue
        selected_time = time[mask]
        selected = current[mask]
        if hasattr(np, "trapezoid"):
            integral = np.trapezoid(selected * selected, selected_time)
        else:  # pragma: no cover
            integral = np.trapz(selected * selected, selected_time)
        total += float(integral)
    return float(total * resistance / duration)


def loss_summary_table(accounting: Any) -> list[dict[str, float | str]]:
    """把 :class:`PowerAccounting` 转成便于写 CSV 的损耗表。"""
    return [
        {"item": "mosfet_network", "power_w": accounting.mosfet_network_average_power_w},
        {"item": "diode", "power_w": accounting.diode_average_power_w},
        {"item": "inductor_dcr", "power_w": accounting.dcr_loss_w},
        {"item": "capacitor_esr", "power_w": accounting.esr_loss_w},
        {"item": "gate_resistor", "power_w": accounting.gate_resistor_loss_w},
        {"item": "gate_pulldown", "power_w": accounting.pulldown_loss_w},
        {"item": "total", "power_w": accounting.total_loss_w},
    ]


def component_loss_fractions(accounting: Any) -> dict[str, float]:
    """各分量占总损耗比例。"""
    total = float(accounting.total_loss_w)
    if total <= 0:
        return {}
    return {
        "mosfet_network": accounting.mosfet_network_average_power_w / total,
        "diode": accounting.diode_average_power_w / total,
        "inductor_dcr": accounting.dcr_loss_w / total,
        "capacitor_esr": accounting.esr_loss_w / total,
        "gate_resistor": accounting.gate_resistor_loss_w / total,
        "gate_pulldown": accounting.pulldown_loss_w / total,
    }


def average_load_power(time_s: Any, output_voltage_v: Any, load_resistance_ohm: float) -> float:
    """按恒阻负载计算输出平均功率。"""
    resistance = positive_number(load_resistance_ohm, "load_resistance_ohm")
    voltage = np.array(output_voltage_v, dtype=float, copy=True)
    time = np.array(time_s, dtype=float, copy=True)
    if voltage.shape != time.shape:
        raise ValueError("output voltage does not match the time axis")
    return average_power(time, voltage, voltage / resistance)


def average_value(time_s: Any, values: Any) -> float:
    """便捷封装：真实波形时间平均。"""
    return time_average(time_s, values)

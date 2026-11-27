"""器件应力统计（全部来自真实波形）。

本模块只报告峰值、有效值与变化率，不声明器件安全工作区（SOA）合格，
也不等价于硬件保护或热设计验证。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from circuits.validators import finite_number


@dataclass(frozen=True)
class DeviceStress:
    """一段窗口内的电压 / 电流应力。"""

    window_start_s: float
    window_end_s: float
    input_voltage_max_v: float
    switch_node_min_v: float
    switch_node_max_v: float
    mosfet_vds_max_v: float
    mosfet_vds_min_v: float
    drain_current_peak_a: float
    drain_current_p999_a: float
    drain_current_min_a: float
    gate_source_voltage_max_v: float
    gate_source_voltage_min_v: float
    drive_command_max_v: float
    diode_reverse_voltage_peak_v: float
    diode_forward_voltage_peak_v: float
    diode_forward_current_peak_a: float
    diode_current_min_a: float
    inductor_current_peak_a: float
    inductor_current_valley_a: float
    inductor_current_ripple_a: float
    capacitor_voltage_max_v: float
    capacitor_voltage_min_v: float
    capacitor_esr_voltage_peak_v: float
    vds_slew_max_v_per_s: float
    vds_slew_p99_v_per_s: float
    current_slew_max_a_per_s: float
    current_slew_p99_a_per_s: float
    data_source: str = "spice_simulation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start_s": self.window_start_s,
            "window_end_s": self.window_end_s,
            "input_voltage_max_v": self.input_voltage_max_v,
            "switch_node_min_v": self.switch_node_min_v,
            "switch_node_max_v": self.switch_node_max_v,
            "mosfet_vds_max_v": self.mosfet_vds_max_v,
            "mosfet_vds_min_v": self.mosfet_vds_min_v,
            "drain_current_peak_a": self.drain_current_peak_a,
            "drain_current_p999_a": self.drain_current_p999_a,
            "drain_current_min_a": self.drain_current_min_a,
            "gate_source_voltage_max_v": self.gate_source_voltage_max_v,
            "gate_source_voltage_min_v": self.gate_source_voltage_min_v,
            "drive_command_max_v": self.drive_command_max_v,
            "diode_reverse_voltage_peak_v": self.diode_reverse_voltage_peak_v,
            "diode_forward_voltage_peak_v": self.diode_forward_voltage_peak_v,
            "diode_forward_current_peak_a": self.diode_forward_current_peak_a,
            "diode_current_min_a": self.diode_current_min_a,
            "inductor_current_peak_a": self.inductor_current_peak_a,
            "inductor_current_valley_a": self.inductor_current_valley_a,
            "inductor_current_ripple_a": self.inductor_current_ripple_a,
            "capacitor_voltage_max_v": self.capacitor_voltage_max_v,
            "capacitor_voltage_min_v": self.capacitor_voltage_min_v,
            "capacitor_esr_voltage_peak_v": self.capacitor_esr_voltage_peak_v,
            "vds_slew_max_v_per_s": self.vds_slew_max_v_per_s,
            "vds_slew_p99_v_per_s": self.vds_slew_p99_v_per_s,
            "current_slew_max_a_per_s": self.current_slew_max_a_per_s,
            "current_slew_p99_a_per_s": self.current_slew_p99_a_per_s,
            "limitations": [
                "peak stress is not a proven safe operating area",
                "no thermal derating, avalanche or short-circuit model",
                "drain_current_peak_a is the raw absolute maximum and can be a single "
                "switching-edge numerical sample; drain_current_p999_a is the robust value",
            ],
            "data_source": self.data_source,
        }


def _array(frame: pd.DataFrame, name: str) -> np.ndarray:
    if name not in frame.columns:
        raise ValueError(f"missing required waveform column: {name}")
    values = frame[name].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{name} contains NaN or Infinity")
    return values


def _slew(time_s: np.ndarray, values: np.ndarray) -> tuple[float, float]:
    dt = np.diff(time_s)
    if np.any(dt <= 0):
        raise ValueError("time axis must be strictly increasing")
    slew = np.abs(np.diff(values) / dt)
    if slew.size == 0:
        return 0.0, 0.0
    return float(np.max(slew)), float(np.percentile(slew, 99.0))


def compute_device_stress(frame: pd.DataFrame) -> DeviceStress:
    """从统一波形帧计算电压、电流与变化率应力。"""
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("frame must be a pandas.DataFrame")
    if len(frame) < 3:
        raise ValueError("stress analysis needs at least three samples")

    time = _array(frame, "time_s")
    if not np.all(np.diff(time) > 0):
        raise ValueError("time_s must be strictly increasing")

    vin = _array(frame, "vin_v")
    vsw = _array(frame, "switch_node_v")
    vds = _array(frame, "mosfet_vds_v")
    vgs = _array(frame, "mosfet_vgs_v")
    drive = _array(frame, "drive_vgs_command_v")
    drain = _array(frame, "mosfet_drain_terminal_current_a")
    diode_v = _array(frame, "diode_anode_cathode_voltage_v")
    diode_i = _array(frame, "diode_current_a")
    il = _array(frame, "inductor_current_a")
    cap_v = _array(frame, "capacitor_internal_voltage_v")
    esr_v = _array(frame, "capacitor_esr_voltage_v")

    vds_slew_max, vds_slew_p99 = _slew(time, vds)
    current_slew_max, current_slew_p99 = _slew(time, drain)

    return DeviceStress(
        window_start_s=float(time[0]),
        window_end_s=float(time[-1]),
        input_voltage_max_v=float(np.max(vin)),
        switch_node_min_v=float(np.min(vsw)),
        switch_node_max_v=float(np.max(vsw)),
        mosfet_vds_max_v=float(np.max(vds)),
        mosfet_vds_min_v=float(np.min(vds)),
        drain_current_peak_a=float(np.max(drain)),
        drain_current_p999_a=float(np.percentile(np.abs(drain), 99.9)),
        drain_current_min_a=float(np.min(drain)),
        gate_source_voltage_max_v=float(np.max(vgs)),
        gate_source_voltage_min_v=float(np.min(vgs)),
        drive_command_max_v=float(np.max(drive)),
        diode_reverse_voltage_peak_v=float(max(0.0, -np.min(diode_v))),
        diode_forward_voltage_peak_v=float(max(0.0, np.max(diode_v))),
        diode_forward_current_peak_a=float(np.max(diode_i)),
        diode_current_min_a=float(np.min(diode_i)),
        inductor_current_peak_a=float(np.max(il)),
        inductor_current_valley_a=float(np.min(il)),
        inductor_current_ripple_a=float(np.max(il) - np.min(il)),
        capacitor_voltage_max_v=float(np.max(cap_v)),
        capacitor_voltage_min_v=float(np.min(cap_v)),
        capacitor_esr_voltage_peak_v=float(np.max(np.abs(esr_v))),
        vds_slew_max_v_per_s=vds_slew_max,
        vds_slew_p99_v_per_s=vds_slew_p99,
        current_slew_max_a_per_s=current_slew_max,
        current_slew_p99_a_per_s=current_slew_p99,
    )


def check_stress(
    stress: DeviceStress,
    *,
    maximum_drain_current_a: float,
    maximum_vds_v: float,
    maximum_gate_voltage_v: float,
    maximum_diode_forward_current_a: float,
) -> dict[str, Any]:
    """按用户给定的教学限值检查应力（不是器件数据手册判据）。"""
    if not isinstance(stress, DeviceStress):
        raise ValueError("stress must be DeviceStress")
    limits = {
        "drain_current": (stress.drain_current_peak_a, positive_limit(maximum_drain_current_a)),
        "vds": (stress.mosfet_vds_max_v, positive_limit(maximum_vds_v)),
        "gate_voltage": (stress.gate_source_voltage_max_v, positive_limit(maximum_gate_voltage_v)),
        "diode_forward_current": (
            stress.diode_forward_current_peak_a,
            positive_limit(maximum_diode_forward_current_a),
        ),
    }
    checks = {
        name: {
            "value": value,
            "limit": limit,
            "passed": bool(value <= limit),
        }
        for name, (value, limit) in limits.items()
    }
    return {
        "passed": all(item["passed"] for item in checks.values()),
        "checks": checks,
        "note": "limits are user-provided teaching limits, not manufacturer ratings",
    }


def positive_limit(value: float) -> float:
    limit = finite_number(value, "limit")
    if limit <= 0:
        raise ValueError("stress limit must be positive")
    return limit

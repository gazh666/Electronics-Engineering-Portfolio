"""真实功率积分与效率计算。

所有平均功率都用时间积分而不是 ``mean(V) * mean(I)``：

    P_avg = (1 / (t1 - t0)) * ∫ V(t) I(t) dt

这样在开关波形上不会把不同相位的电压、电流均值错误相乘。

端口符号约定（与 :mod:`analysis.buck_waveforms` 一致）：

- 输入功率 ``P_in = <V(vin) * I_in>``，``I_in = -i(VIN)``
- 驱动功率 ``P_drv = <V(drv)-V(sw) * I_drv>``，``I_drv = -i(VDRV)``
- 输出功率 ``P_out = <V(out) * I_load>``
- MOSFET 网络功率 ``P_sw = <V_DS * I_D> + <V_GS * I_G>``
- 二极管功率 ``P_d = <V_AK * I_D>``（不做 ``max(0, ...)`` 截断）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd

from circuits.validators import finite_number, nonnegative_number, positive_number

#: 效率超过该值时标记为需要审查，而不是截断为 100%。
EFFICIENCY_REVIEW_THRESHOLD_PERCENT = 100.5


def _trapezoid(values: np.ndarray, time: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(values, time))
    return float(np.trapz(values, time))  # pragma: no cover - numpy < 2.0


def _waveform(values: Any, name: str) -> np.ndarray:
    array = np.array(values, dtype=float, copy=True)
    if array.ndim != 1 or array.size < 2:
        raise ValueError(f"{name} must be a 1D waveform with at least two samples")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains NaN or Infinity")
    return array


def _time_axis(time_s: Any) -> np.ndarray:
    time = _waveform(time_s, "time_s")
    steps = np.diff(time)
    if np.any(steps <= 0):
        raise ValueError("time_s must be strictly increasing")
    return time


def _aligned(values: Any, time: np.ndarray, name: str) -> np.ndarray:
    array = _waveform(values, name)
    if array.shape != time.shape:
        raise ValueError(f"{name} length does not match the time axis")
    return array


def time_average(time_s: Any, values: Any) -> float:
    """时间加权平均。"""
    time = _time_axis(time_s)
    wave = _aligned(values, time, "values")
    duration = float(time[-1] - time[0])
    if duration <= 0:
        raise ValueError("time window must have positive duration")
    return _trapezoid(wave, time) / duration


def rms_value(time_s: Any, values: Any) -> float:
    """时间加权有效值。"""
    time = _time_axis(time_s)
    wave = _aligned(values, time, "values")
    duration = float(time[-1] - time[0])
    if duration <= 0:
        raise ValueError("time window must have positive duration")
    return float(np.sqrt(max(_trapezoid(wave * wave, time) / duration, 0.0)))


def integrated_power(time_s: Any, voltage_v: Any, current_a: Any) -> float:
    """瞬时功率的积分（焦耳）。"""
    time = _time_axis(time_s)
    voltage = _aligned(voltage_v, time, "voltage_v")
    current = _aligned(current_a, time, "current_a")
    return _trapezoid(voltage * current, time)


def average_power(time_s: Any, voltage_v: Any, current_a: Any) -> float:
    """时间平均端口功率（瓦特）。"""
    time = _time_axis(time_s)
    duration = float(time[-1] - time[0])
    if duration <= 0:
        raise ValueError("time window must have positive duration")
    return integrated_power(time, voltage_v, current_a) / duration


def rms_current_from_resistance_loss(loss_w: float, resistance_ohm: float) -> float:
    """由电阻损耗反推等效有效电流。"""
    resistance = positive_number(resistance_ohm, "resistance_ohm")
    loss = nonnegative_number(loss_w, "loss_w")
    return float(np.sqrt(loss / resistance))


def efficiency_percent(output_power_w: float, input_power_w: float) -> tuple[float | None, str]:
    """返回效率百分比与状态说明；输入功率非正时效率不可定义。"""
    output = finite_number(output_power_w, "output_power_w")
    supplied = finite_number(input_power_w, "input_power_w")
    if supplied <= 0:
        return None, "input_power_not_positive"
    value = 100.0 * output / supplied
    if not np.isfinite(value):
        return None, "efficiency_not_finite"
    if value > EFFICIENCY_REVIEW_THRESHOLD_PERCENT:
        return float(value), "efficiency_above_100_check_boundaries"
    if value < 0:
        return float(value), "negative_efficiency_check_signs"
    return float(value), "ok"


def frame_window(frame: pd.DataFrame, start_s: float, end_s: float) -> pd.DataFrame:
    """截取 ``[start_s, end_s]`` 时间窗口，保留边界采样点。"""
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("frame must be a pandas.DataFrame")
    if "time_s" not in frame.columns:
        raise ValueError("frame must contain a time_s column")
    start = finite_number(start_s, "start_s")
    end = finite_number(end_s, "end_s")
    if end <= start:
        raise ValueError("end_s must be greater than start_s")
    time = frame["time_s"].to_numpy(dtype=float)
    mask = (time >= start) & (time <= end)
    window = frame.loc[mask].reset_index(drop=True)
    if len(window) < 3:
        raise ValueError("selected window contains too few samples")
    return window


@dataclass(frozen=True)
class PowerAccounting:
    """一段稳态窗口内的功率与损耗核算结果。"""

    window_start_s: float
    window_end_s: float
    duration_s: float
    input_average_power_w: float
    driver_average_power_w: float
    output_average_power_w: float
    mosfet_network_average_power_w: float
    diode_average_power_w: float
    dcr_loss_w: float
    esr_loss_w: float
    gate_resistor_loss_w: float
    pulldown_loss_w: float
    total_loss_w: float
    residual_w: float
    efficiency_power_stage_percent: float | None
    efficiency_system_percent: float | None
    efficiency_status: str
    inductor_current_rms_a: float
    capacitor_current_rms_a: float
    input_current_average_a: float
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start_s": self.window_start_s,
            "window_end_s": self.window_end_s,
            "duration_s": self.duration_s,
            "input_average_power_w": self.input_average_power_w,
            "driver_average_power_w": self.driver_average_power_w,
            "output_average_power_w": self.output_average_power_w,
            "mosfet_network_average_power_w": self.mosfet_network_average_power_w,
            "diode_average_power_w": self.diode_average_power_w,
            "dcr_loss_w": self.dcr_loss_w,
            "esr_loss_w": self.esr_loss_w,
            "gate_resistor_loss_w": self.gate_resistor_loss_w,
            "pulldown_loss_w": self.pulldown_loss_w,
            "total_loss_w": self.total_loss_w,
            "residual_w": self.residual_w,
            "efficiency_power_stage_percent": self.efficiency_power_stage_percent,
            "efficiency_system_percent": self.efficiency_system_percent,
            "efficiency_status": self.efficiency_status,
            "inductor_current_rms_a": self.inductor_current_rms_a,
            "capacitor_current_rms_a": self.capacitor_current_rms_a,
            "input_current_average_a": self.input_current_average_a,
            "notes": list(self.notes),
            "method": "time_integral_of_instantaneous_power",
            "data_source": "spice_simulation",
        }


_POWER_COLUMN_HINTS = (
    "time_s",
    "vin_v",
    "vout_v",
    "input_current_a",
    "load_current_a",
)


def compute_power_accounting(
    frame: pd.DataFrame,
    *,
    dcr_ohm: float = 0.0,
    esr_ohm: float = 0.0,
    gate_resistance_ohm: float = 0.0,
    pulldown_resistance_ohm: float = 0.0,
) -> PowerAccounting:
    """按真实波形计算输入、输出、各损耗、残差与效率。"""
    from .loss_analysis import (
        capacitor_esr_loss,
        diode_loss,
        gate_network_losses,
        inductor_dcr_loss,
        mosfet_network_loss,
    )

    required = (
        "time_s",
        "vin_v",
        "vout_v",
        "input_current_a",
        "load_current_a",
        "mosfet_vds_v",
        "mosfet_drain_terminal_current_a",
        "mosfet_vgs_v",
        "gate_current_a",
        "diode_anode_cathode_voltage_v",
        "diode_current_a",
        "inductor_current_a",
        "capacitor_current_a",
        "driver_current_a",
        "drive_vgs_command_v",
    )
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"power accounting requires columns: {missing}")
    if len(frame) < 3:
        raise ValueError("power accounting window needs at least three samples")

    dcr = nonnegative_number(dcr_ohm, "dcr_ohm")
    esr = nonnegative_number(esr_ohm, "esr_ohm")
    rg = nonnegative_number(gate_resistance_ohm, "gate_resistance_ohm")
    rgs = nonnegative_number(pulldown_resistance_ohm, "pulldown_resistance_ohm")

    time = _time_axis(frame["time_s"].to_numpy(dtype=float))
    duration = float(time[-1] - time[0])

    input_power = average_power(time, frame["vin_v"], frame["input_current_a"])
    driver_power = average_power(
        time, frame["drive_vgs_command_v"], frame["driver_current_a"]
    )
    output_power = average_power(time, frame["vout_v"], frame["load_current_a"])

    mosfet_loss = mosfet_network_loss(
        time,
        frame["mosfet_vds_v"],
        frame["mosfet_drain_terminal_current_a"],
        frame["mosfet_vgs_v"],
        frame["gate_current_a"],
    )
    diode_power = diode_loss(
        time, frame["diode_anode_cathode_voltage_v"], frame["diode_current_a"]
    )
    dcr_loss = inductor_dcr_loss(time, frame["inductor_current_a"], dcr)
    esr_loss = capacitor_esr_loss(time, frame["capacitor_current_a"], esr)
    gate_losses = gate_network_losses(
        time,
        drive_voltage_v=frame["drive_vgs_command_v"],
        gate_voltage_v=frame["mosfet_vgs_v"],
        gate_current_a=frame["gate_current_a"],
        gate_resistance_ohm=rg,
        pulldown_resistance_ohm=rgs,
    )

    total_loss = (
        mosfet_loss
        + diode_power
        + dcr_loss
        + esr_loss
        + gate_losses["gate_resistor_loss_w"]
        + gate_losses["pulldown_loss_w"]
    )
    residual = input_power + driver_power - output_power - total_loss

    efficiency_power_stage, status = efficiency_percent(output_power, input_power)
    efficiency_system, system_status = efficiency_percent(
        output_power, input_power + driver_power
    )
    notes: list[str] = [
        "power averaged by integrating instantaneous v(t)*i(t) over the window",
        "MOSFET network boundary: drain and gate terminals referenced to the switch node; "
        "gate resistor and pulldown resistor are counted separately",
    ]
    if status != "ok":
        notes.append(f"power-stage efficiency status: {status}")
    if system_status != "ok":
        notes.append(f"system efficiency status: {system_status}")

    return PowerAccounting(
        window_start_s=float(time[0]),
        window_end_s=float(time[-1]),
        duration_s=duration,
        input_average_power_w=float(input_power),
        driver_average_power_w=float(driver_power),
        output_average_power_w=float(output_power),
        mosfet_network_average_power_w=float(mosfet_loss),
        diode_average_power_w=float(diode_power),
        dcr_loss_w=float(dcr_loss),
        esr_loss_w=float(esr_loss),
        gate_resistor_loss_w=float(gate_losses["gate_resistor_loss_w"]),
        pulldown_loss_w=float(gate_losses["pulldown_loss_w"]),
        total_loss_w=float(total_loss),
        residual_w=float(residual),
        efficiency_power_stage_percent=efficiency_power_stage,
        efficiency_system_percent=efficiency_system,
        efficiency_status=status if system_status == "ok" else f"{status};{system_status}",
        inductor_current_rms_a=rms_value(time, frame["inductor_current_a"]),
        capacitor_current_rms_a=rms_value(time, frame["capacitor_current_a"]),
        input_current_average_a=time_average(time, frame["input_current_a"]),
        notes=tuple(notes),
    )


def loss_fractions(accounting: PowerAccounting) -> dict[str, float]:
    """返回各损耗占总损耗的比例（总损耗为 0 时返回空字典）。"""
    if not isinstance(accounting, PowerAccounting):
        raise ValueError("accounting must be PowerAccounting")
    total = accounting.total_loss_w
    if total <= 0:
        return {}
    return {
        "mosfet": accounting.mosfet_network_average_power_w / total,
        "diode": accounting.diode_average_power_w / total,
        "dcr": accounting.dcr_loss_w / total,
        "esr": accounting.esr_loss_w / total,
        "gate_resistor": accounting.gate_resistor_loss_w / total,
        "pulldown": accounting.pulldown_loss_w / total,
    }


def relative_residual(accounting: PowerAccounting) -> float:
    """残差相对于总输入功率的比例（用于数据质量判据）。"""
    supplied = accounting.input_average_power_w + accounting.driver_average_power_w
    if supplied <= 0:
        return float("nan")
    return accounting.residual_w / supplied


def require_columns(frame: Mapping[str, Any] | pd.DataFrame) -> None:
    """校验导出所需基础列存在（供脚本显式调用）。"""
    if isinstance(frame, pd.DataFrame):
        missing = [name for name in _POWER_COLUMN_HINTS if name not in frame.columns]
        if missing:
            raise ValueError(f"missing columns: {missing}")

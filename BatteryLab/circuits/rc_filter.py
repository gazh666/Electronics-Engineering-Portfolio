"""单差分通道 RC 输入滤波（Task 10/11/12）。

拓扑（独立教学通道）：

    VHIGH -- Rh -- SENSE_H
    VLOW  -- Rl -- SENSE_L
    Cdiff 接在 SENSE_H 与 SENSE_L 之间

差分等效电阻 Rdiff = Rh + Rl；tau = Rdiff*C；fc = 1/(2*pi*Rdiff*C)。
完整 3S AFE 存在共享节点与相邻电容耦合，因此本独立通道结论不能直接
外推到 BQ76922 完整外围网络。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_F, u_Hz, u_Ohm, u_V

from circuits.spice_utils import run_ac_sweep, run_transient


class RCFilterError(ValueError):
    """RC 滤波参数非法。"""


BLEED_OHM = 1.0e9


@dataclass(frozen=True)
class RCFilterConfig:
    series_resistance_ohm: float
    differential_capacitance_f: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.series_resistance_ohm) or self.series_resistance_ohm <= 0.0:
            raise RCFilterError("串联电阻必须为正")
        if not math.isfinite(self.differential_capacitance_f) or self.differential_capacitance_f <= 0.0:
            raise RCFilterError("差分电容必须为正")

    @property
    def differential_resistance_ohm(self) -> float:
        return 2.0 * self.series_resistance_ohm

    @property
    def tau_s(self) -> float:
        return self.differential_resistance_ohm * self.differential_capacitance_f

    @property
    def cutoff_hz(self) -> float:
        return 1.0 / (2.0 * math.pi * self.tau_s)


def theoretical_cutoff_hz(series_resistance_ohm: float, differential_capacitance_f: float) -> float:
    return RCFilterConfig(series_resistance_ohm, differential_capacitance_f).cutoff_hz


def theoretical_rise_time_s(series_resistance_ohm: float, differential_capacitance_f: float) -> float:
    return 2.197 * RCFilterConfig(series_resistance_ohm, differential_capacitance_f).tau_s


def theoretical_settling_time_s(series_resistance_ohm: float, differential_capacitance_f: float) -> float:
    return 4.605 * RCFilterConfig(series_resistance_ohm, differential_capacitance_f).tau_s


def _build_ac(config: RCFilterConfig) -> Circuit:
    circuit = Circuit("BatteryLab differential RC filter AC")
    circuit.SinusoidalVoltageSource("src", "hi", "lo", amplitude=0.0 @ u_V, ac_magnitude=1.0 @ u_V)
    circuit.R("rh", "hi", "sh", config.series_resistance_ohm)
    circuit.R("rl", "lo", "sl", config.series_resistance_ohm)
    circuit.C("cd", "sh", "sl", config.differential_capacitance_f)
    circuit.R("bleed_h", "hi", circuit.gnd, BLEED_OHM)
    circuit.R("bleed_l", "lo", circuit.gnd, BLEED_OHM)
    return circuit


def run_ac_response(
    config: RCFilterConfig,
    *,
    start_hz: float = 10.0,
    stop_hz: float = 10.0e6,
    points_per_decade: int = 50,
) -> dict[str, np.ndarray]:
    circuit = _build_ac(config)
    data = run_ac_sweep(
        circuit,
        start_hz=start_hz,
        stop_hz=stop_hz,
        points_per_decade=points_per_decade,
        nodes=["sh", "sl", "hi", "lo"],
    )
    denominator = data["hi"] - data["lo"]
    numerator = data["sh"] - data["sl"]
    transfer = numerator / denominator
    return {
        "frequency_hz": data["frequency_hz"],
        "transfer": transfer,
        "gain_db": 20.0 * np.log10(np.abs(transfer)),
        "phase_deg": np.degrees(np.angle(transfer)),
    }


def extract_cutoff(frequency_hz: np.ndarray, transfer: np.ndarray) -> float:
    magnitude = np.abs(transfer)
    low_frequency_gain = float(magnitude[0])
    target = low_frequency_gain / math.sqrt(2.0)
    for index in range(1, len(magnitude)):
        if magnitude[index] <= target <= magnitude[index - 1]:
            f0, f1 = frequency_hz[index - 1], frequency_hz[index]
            m0, m1 = magnitude[index - 1], magnitude[index]
            log_interp = (math.log10(f0) + (target - m0) / (m1 - m0) * (math.log10(f1) - math.log10(f0)))
            return float(10.0**log_interp)
    return float("nan")


def attenuation_db(frequency_hz: np.ndarray, gain_db: np.ndarray, at_hz: float) -> float:
    value = float(np.interp(math.log10(at_hz), np.log10(frequency_hz), gain_db))
    return value


def _build_step(config: RCFilterConfig, step_v: float, t_step_s: float, rise_s: float, duration_s: float) -> Circuit:
    circuit = Circuit("BatteryLab differential RC filter step")
    values = [(0.0, 0.0), (t_step_s, 0.0), (t_step_s + rise_s, float(step_v)), (duration_s, float(step_v))]
    circuit.PieceWiseLinearVoltageSource("src", "hi", "lo", values=values)
    circuit.R("rh", "hi", "sh", config.series_resistance_ohm)
    circuit.R("rl", "lo", "sl", config.series_resistance_ohm)
    circuit.C("cd", "sh", "sl", config.differential_capacitance_f)
    circuit.R("bleed_h", "hi", circuit.gnd, BLEED_OHM)
    circuit.R("bleed_l", "lo", circuit.gnd, BLEED_OHM)
    return circuit


def run_step_response(
    config: RCFilterConfig,
    *,
    step_v: float = 1.0,
    t_step_s: float = 1.0e-3,
    rise_s: float = 1.0e-6,
    duration_s: float | None = None,
    step_s: float = 1.0e-6,
) -> dict[str, object]:
    duration = duration_s or t_step_s + 14.0 * config.tau_s
    circuit = _build_step(config, step_v, t_step_s, rise_s, duration)
    data = run_transient(
        circuit,
        duration_s=duration,
        step_s=step_s,
        max_step_s=step_s,
        nodes=["sh", "sl", "hi", "lo"],
    )
    time_s = data["time_s"]
    output = data["sh"] - data["sl"]
    return _step_metrics(time_s, output, step_v, t_step_s, rise_s)


def _step_metrics(time_s: np.ndarray, output: np.ndarray, step_v: float, t_step_s: float, rise_s: float) -> dict[str, object]:
    tail = output[time_s >= time_s[-1] - 0.05 * (time_s[-1] - time_s[0])]
    final = float(np.mean(tail))
    start_value = 0.0
    amplitude = final - start_value
    if abs(amplitude) <= 1e-15:
        raise RCFilterError("阶跃响应幅度接近 0")

    def crossing(fraction: float) -> float:
        target = start_value + fraction * amplitude
        for index in range(1, len(time_s)):
            if (output[index - 1] - target) * (output[index] - target) <= 0.0 and output[index] != output[index - 1]:
                fraction_interp = (target - output[index - 1]) / (output[index] - output[index - 1])
                return float(time_s[index - 1] + fraction_interp * (time_s[index] - time_s[index - 1]))
        return float("nan")

    t10 = crossing(0.1)
    t90 = crossing(0.9)
    t63 = crossing(0.632)
    overshoot = float(max(0.0, (np.max(output) - final) / amplitude * 100.0))
    tolerance = 0.01 * abs(amplitude)
    outside = np.where(np.abs(output - final) > tolerance)[0]
    settling = float(time_s[outside[-1]] - t_step_s) if outside.size else 0.0
    return {
        "time_s": time_s,
        "output_v": output,
        "final_v": final,
        "rise_time_10_90_s": float(t90 - t10),
        "time_63p2_s": float(t63 - t_step_s),
        "settling_time_1pct_s": settling,
        "overshoot_percent": overshoot,
        "steady_state_error_v": float(final - step_v),
        "step_start_s": float(t_step_s),
        "rise_s": float(rise_s),
    }


def _build_interference(
    config: RCFilterConfig,
    *,
    differential_amplitude_v: float,
    common_mode_amplitude_v: float,
    frequency_hz: float,
    duration_s: float,
) -> Circuit:
    circuit = Circuit("BatteryLab differential RC filter interference")
    high_amplitude = differential_amplitude_v + common_mode_amplitude_v
    low_amplitude = -differential_amplitude_v + common_mode_amplitude_v
    circuit.SinusoidalVoltageSource("vhi", "hi", circuit.gnd, amplitude=high_amplitude @ u_V, frequency=frequency_hz @ u_Hz)
    circuit.SinusoidalVoltageSource("vlo", "lo", circuit.gnd, amplitude=low_amplitude @ u_V, frequency=frequency_hz @ u_Hz)
    circuit.R("rh", "hi", "sh", config.series_resistance_ohm)
    circuit.R("rl", "lo", "sl", config.series_resistance_ohm)
    circuit.C("cd", "sh", "sl", config.differential_capacitance_f)
    return circuit


def _amplitude_at(time_s: np.ndarray, signal: np.ndarray, frequency_hz: float) -> float:
    mask = time_s >= 0.5 * time_s[-1]
    t = time_s[mask]
    y = signal[mask]
    uniform = np.linspace(t[0], t[-1], 2000)
    resampled = np.interp(uniform, t, y)
    omega = 2.0 * math.pi * frequency_hz
    design = np.column_stack([np.sin(omega * uniform), np.cos(omega * uniform)])
    coefficients, *_ = np.linalg.lstsq(design, resampled, rcond=None)
    return float(math.hypot(coefficients[0], coefficients[1]))


def run_interference(
    config: RCFilterConfig,
    *,
    differential_amplitude_v: float = 0.1,
    common_mode_amplitude_v: float = 0.1,
    frequency_hz: float = 100.0e3,
    duration_s: float = 1.0e-3,
    max_step_s: float = 1.0e-7,
) -> dict[str, object]:
    circuit = _build_interference(
        config,
        differential_amplitude_v=differential_amplitude_v,
        common_mode_amplitude_v=common_mode_amplitude_v,
        frequency_hz=frequency_hz,
        duration_s=duration_s,
    )
    data = run_transient(
        circuit,
        duration_s=duration_s,
        step_s=max_step_s,
        max_step_s=max_step_s,
        nodes=["sh", "sl", "hi", "lo"],
    )
    time_s = data["time_s"]
    before = data["hi"] - data["lo"]
    after = data["sh"] - data["sl"]
    mask = time_s >= 0.5 * duration_s
    rms_before = float(np.sqrt(np.mean(before[mask] ** 2)))
    rms_after = float(np.sqrt(np.mean(after[mask] ** 2)))
    return {
        "time_s": time_s,
        "before_v": before,
        "after_v": after,
        "rms_before_v": rms_before,
        "rms_after_v": rms_after,
        "attenuation_db": 20.0 * math.log10(rms_after / rms_before) if rms_before > 0 else float("nan"),
        "amplitude_before_v": _amplitude_at(time_s, before, frequency_hz),
        "amplitude_after_v": _amplitude_at(time_s, after, frequency_hz),
        "frequency_hz": float(frequency_hz),
        "common_mode_amplitude_v": float(common_mode_amplitude_v),
        "differential_amplitude_v": float(differential_amplitude_v),
    }


def scan_parameters(
    resistances_ohm: Sequence[float],
    capacitances_f: Sequence[float],
    *,
    run_step: bool = True,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for resistance in resistances_ohm:
        for capacitance in capacitances_f:
            config = RCFilterConfig(float(resistance), float(capacitance))
            ac = run_ac_response(config)
            cutoff = extract_cutoff(ac["frequency_hz"], ac["transfer"])
            attenuation_100k = attenuation_db(ac["frequency_hz"], ac["gain_db"], 100.0e3)
            row: dict[str, object] = {
                "resistance_ohm": config.series_resistance_ohm,
                "capacitance_f": config.differential_capacitance_f,
                "differential_resistance_ohm": config.differential_resistance_ohm,
                "tau_s": config.tau_s,
                "theoretical_cutoff_hz": config.cutoff_hz,
                "spice_cutoff_hz": cutoff,
                "cutoff_error_percent": (cutoff - config.cutoff_hz) / config.cutoff_hz * 100.0,
                "attenuation_100khz_db": attenuation_100k,
                "cutoff_frequency_hz": ac["frequency_hz"],
                "gain_db": ac["gain_db"],
            }
            if run_step:
                step = run_step_response(config, step_v=0.1, t_step_s=1.0e-3, rise_s=1.0e-6)
                row.update(
                    {
                        "rise_time_10_90_s": step["rise_time_10_90_s"],
                        "settling_time_1pct_s": step["settling_time_1pct_s"],
                        "sampling_delay_s": step["time_63p2_s"],
                        "steady_state_error_v": step["steady_state_error_v"],
                    }
                )
            rows.append(row)
    return rows

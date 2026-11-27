"""系统损耗分解（基于真实波形，不是估算表）。"""

from __future__ import annotations

from typing import Any

from validation.system_energy_validator import trapezoid_energy


def breakdown_from_waveform(
    waveform: dict[str, list[float]],
    *,
    path_resistance_ohm: float,
    battery_internal_resistance_ohm: float,
    steady_window_start_s: float,
) -> dict[str, Any]:
    time_s = waveform["time_s"]
    mask_indices = [index for index, value in enumerate(time_s) if value >= steady_window_start_s]
    if len(mask_indices) < 100:
        raise ValueError("稳态窗口样本不足")
    start, end = mask_indices[0], mask_indices[-1] + 1

    def window(name: str) -> list[float]:
        return waveform[name][start:end]

    t = window("time_s")
    ibat = window("battery_current_a")
    vin = window("converter_input_voltage_v")
    iin = window("converter_input_current_a")
    vout = window("output_voltage_v")
    iout = window("load_current_a")

    battery_internal = trapezoid_energy(t, [current**2 * battery_internal_resistance_ohm for current in ibat])
    protection = trapezoid_energy(t, [current**2 * path_resistance_ohm for current in ibat])
    input_energy = trapezoid_energy(t, [a * b for a, b in zip(vin, iin)])
    output_energy = trapezoid_energy(t, [a * b for a, b in zip(vout, iout)])
    converter_loss = input_energy - output_energy
    window_duration = t[-1] - t[0]
    return {
        "window_s": [t[0], t[-1]],
        "window_duration_s": window_duration,
        "battery_internal_loss_j": battery_internal,
        "protection_path_loss_j": protection,
        "converter_loss_j": converter_loss,
        "output_energy_j": output_energy,
        "converter_input_energy_j": input_energy,
        "battery_internal_loss_w": battery_internal / window_duration if window_duration > 0 else None,
        "protection_path_loss_w": protection / window_duration if window_duration > 0 else None,
        "converter_loss_w": converter_loss / window_duration if window_duration > 0 else None,
        "output_power_w": output_energy / window_duration if window_duration > 0 else None,
        "note": "Buck 损耗为 Pin-Pout 之差，包含开关与导通损耗，无法分离验证",
    }


__all__ = ["breakdown_from_waveform"]

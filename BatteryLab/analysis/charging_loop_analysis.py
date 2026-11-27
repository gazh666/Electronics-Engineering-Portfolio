"""CC-CV 双闭环小信号频域分析。

模型层次：Buck 平均状态空间小信号 + 电池一阶 RC 阻抗 + PI 控制器。
这是"平均模型/线性化"结论，不是开关级稳定性证明；最终仍需真实 SPICE 波形复核。

电压环对象取电池阻抗，是因为充电稳态下电池电流是受控量，端电压由
``OCV + I·Z(s)`` 决定；输出电容电流只在瞬态中显著，本分析的带宽远低于其影响区。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np


def default_frequency_grid(
    start_hz: float = 1.0e-2,
    stop_hz: float = 1.0e6,
    points: int = 1201,
) -> np.ndarray:
    if not (math.isfinite(start_hz) and math.isfinite(stop_hz)):
        raise ValueError("频点非法")
    if start_hz <= 0.0 or stop_hz <= start_hz or points < 3:
        raise ValueError("频率范围非法")
    return np.logspace(math.log10(start_hz), math.log10(stop_hz), points)


def _validate_positive(name: str, value: float) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} 必须为正")
    return float(value)


def buck_state_space(
    vin_v: float,
    inductance_h: float,
    capacitance_f: float,
    load_resistance_ohm: float,
    capacitor_esr_ohm: float,
    inductor_dc_resistance_ohm: float = 0.0,
) -> dict[str, Any]:
    """Buck 平均模型（CCM，含电感 DCR 与电容 ESR）的状态矩阵。"""
    vin = _validate_positive("vin_v", vin_v)
    inductance = _validate_positive("inductance_h", inductance_h)
    capacitance = _validate_positive("capacitance_f", capacitance_f)
    load = _validate_positive("load_resistance_ohm", load_resistance_ohm)
    if not math.isfinite(capacitor_esr_ohm) or capacitor_esr_ohm < 0.0:
        raise ValueError("ESR 不能为负")
    if not math.isfinite(inductor_dc_resistance_ohm) or inductor_dc_resistance_ohm < 0.0:
        raise ValueError("DCR 不能为负")
    esr = float(capacitor_esr_ohm)
    dcr = float(inductor_dc_resistance_ohm)

    k = 1.0 + esr / load
    a = np.array(
        [
            [-(esr / (k * inductance) + dcr / inductance), -1.0 / (k * inductance)],
            [(1.0 - esr / (k * load)) / capacitance, -1.0 / (k * load * capacitance)],
        ],
        dtype=float,
    )
    b = np.array([[vin / inductance], [0.0]], dtype=float)
    c_current = np.array([[1.0, 0.0]], dtype=float)
    c_voltage = np.array([[esr / k, 1.0 / k]], dtype=float)
    return {
        "a": a,
        "b": b,
        "c_current": c_current,
        "c_voltage": c_voltage,
        "d": 0.0,
    }


def _state_space_response(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    d: float,
    frequency_hz: Sequence[float],
) -> np.ndarray:
    frequencies = np.asarray(frequency_hz, dtype=float)
    if frequencies.ndim != 1 or frequencies.size < 2:
        raise ValueError("频点序列非法")
    if not np.all(np.isfinite(frequencies)) or np.any(frequencies <= 0.0):
        raise ValueError("频点必须为正")
    response = np.empty(frequencies.size, dtype=complex)
    identity = np.eye(a.shape[0])
    for index, frequency in enumerate(frequencies):
        s = 2j * math.pi * frequency
        state = np.linalg.solve(s * identity - a, b[:, 0])
        response[index] = complex((c @ state)[0]) + d
    return response


def buck_plant_response(
    frequency_hz: Sequence[float],
    vin_v: float,
    inductance_h: float,
    capacitance_f: float,
    load_resistance_ohm: float,
    capacitor_esr_ohm: float,
    inductor_dc_resistance_ohm: float = 0.0,
) -> dict[str, np.ndarray]:
    """返回占空比→电感电流与占空比→输出电压的复频响应。"""
    model = buck_state_space(
        vin_v,
        inductance_h,
        capacitance_f,
        load_resistance_ohm,
        capacitor_esr_ohm,
        inductor_dc_resistance_ohm,
    )
    return {
        "current": _state_space_response(
            model["a"], model["b"], model["c_current"], model["d"], frequency_hz
        ),
        "voltage": _state_space_response(
            model["a"], model["b"], model["c_voltage"], model["d"], frequency_hz
        ),
    }


def pi_response(
    frequency_hz: Sequence[float],
    kp: float,
    ki: float,
) -> np.ndarray:
    if not all(math.isfinite(v) for v in (kp, ki)) or kp < 0.0 or ki < 0.0:
        raise ValueError("PI 参数非法")
    frequencies = np.asarray(frequency_hz, dtype=float)
    if np.any(frequencies <= 0.0):
        raise ValueError("频点必须为正")
    s = 2j * math.pi * frequencies
    return kp + ki / s


def battery_impedance_response(
    frequency_hz: Sequence[float],
    r0_ohm: float,
    r1_ohm: float,
    c1_f: float,
) -> np.ndarray:
    """一阶 RC 电池阻抗 ``Z(s) = R0 + R1 / (1 + s R1 C1)``。"""
    for name, value in (("r0_ohm", r0_ohm), ("r1_ohm", r1_ohm), ("c1_f", c1_f)):
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{name} 非法")
    if r1_ohm > 0.0 and c1_f <= 0.0:
        raise ValueError("存在 R1 时 C1 必须为正")
    frequencies = np.asarray(frequency_hz, dtype=float)
    if np.any(frequencies <= 0.0):
        raise ValueError("频点必须为正")
    s = 2j * math.pi * frequencies
    if r1_ohm == 0.0:
        return np.full(frequencies.shape, complex(r0_ohm))
    return r0_ohm + r1_ohm / (1.0 + s * r1_ohm * c1_f)


def _normalized_phase_deg(phase_deg: np.ndarray) -> np.ndarray:
    return np.where(phase_deg > 0.0, phase_deg - 360.0, phase_deg)


def loop_margins(
    frequency_hz: Sequence[float],
    loop_gain: Sequence[complex],
) -> dict[str, float | None]:
    """由频响计算穿越频率、相位裕度与增益裕度。

    相位裕度 = 180° + ∠T(fc)；增益裕度 = -20log10|T(f180)|。
    找不到穿越点对应返回 ``None``，由调用方按"未验证"处理，禁止当成通过。
    """
    frequencies = np.asarray(frequency_hz, dtype=float)
    gain = np.asarray(loop_gain, dtype=complex)
    if frequencies.shape != gain.shape or frequencies.ndim != 1 or frequencies.size < 3:
        raise ValueError("频响序列非法")
    if not np.all(np.isfinite(frequencies)) or not np.all(np.isfinite(gain)):
        raise ValueError("频响含非有限值")

    log_frequency = np.log10(frequencies)
    magnitude_db = 20.0 * np.log10(np.abs(gain))
    phase_deg = _normalized_phase_deg(np.degrees(np.angle(gain)))

    gain_crossover_hz: float | None = None
    phase_margin_deg: float | None = None
    for index in range(frequencies.size - 1):
        left = magnitude_db[index]
        right = magnitude_db[index + 1]
        if left == 0.0:
            gain_crossover_hz = float(frequencies[index])
            phase_margin_deg = 180.0 + float(phase_deg[index])
            break
        if left * right < 0.0:
            fraction = left / (left - right)
            gain_crossover_hz = float(10.0 ** (log_frequency[index] + fraction * (log_frequency[index + 1] - log_frequency[index])))
            phase = phase_deg[index] + fraction * (phase_deg[index + 1] - phase_deg[index])
            phase_margin_deg = 180.0 + float(phase)
            break

    phase_crossover_hz: float | None = None
    gain_margin_db: float | None = None
    for index in range(frequencies.size - 1):
        left = phase_deg[index]
        right = phase_deg[index + 1]
        if left > -180.0 >= right:
            fraction = (left + 180.0) / (left - right)
            phase_crossover_hz = float(
                10.0 ** (log_frequency[index] + fraction * (log_frequency[index + 1] - log_frequency[index]))
            )
            magnitude = magnitude_db[index] + fraction * (magnitude_db[index + 1] - magnitude_db[index])
            gain_margin_db = -float(magnitude)
            break

    return {
        "gain_crossover_hz": gain_crossover_hz,
        "phase_margin_deg": phase_margin_deg,
        "phase_crossover_hz": phase_crossover_hz,
        "gain_margin_db": gain_margin_db,
        "gain_margin_infinite": bool(
            gain_margin_db is None and float(phase_deg.min()) > -180.0
        ),
        "dc_gain_db": float(magnitude_db[0]),
        "minimum_phase_deg": float(phase_deg.min()),
    }


def analyze_current_loop(
    frequency_hz: Sequence[float],
    vin_v: float,
    inductance_h: float,
    capacitance_f: float,
    load_resistance_ohm: float,
    capacitor_esr_ohm: float,
    kp_duty_per_a: float,
    ki_duty_per_as: float,
    inductor_dc_resistance_ohm: float = 0.0,
) -> dict[str, Any]:
    plant = buck_plant_response(
        frequency_hz,
        vin_v,
        inductance_h,
        capacitance_f,
        load_resistance_ohm,
        capacitor_esr_ohm,
        inductor_dc_resistance_ohm,
    )["current"]
    controller = pi_response(frequency_hz, kp_duty_per_a, ki_duty_per_as)
    gain = controller * plant
    result = loop_margins(frequency_hz, gain)
    result["plant_gain_db"] = float(20.0 * np.log10(abs(plant[0])))
    result["loop_gain"] = gain
    result["plant"] = plant
    return result


def analyze_voltage_loop(
    frequency_hz: Sequence[float],
    battery_r0_ohm: float,
    battery_r1_ohm: float,
    battery_c1_f: float,
    kp_a_per_v: float,
    ki_a_per_vs: float,
    inner_loop_gain: Sequence[complex] | None = None,
) -> dict[str, Any]:
    impedance = battery_impedance_response(frequency_hz, battery_r0_ohm, battery_r1_ohm, battery_c1_f)
    if inner_loop_gain is None:
        inner_closed = np.ones(impedance.shape, dtype=complex)
        inner_approximation = "ideal_current_source"
    else:
        inner = np.asarray(inner_loop_gain, dtype=complex)
        if inner.shape != impedance.shape:
            raise ValueError("内环频响长度不一致")
        inner_closed = inner / (1.0 + inner)
        inner_approximation = "measured_inner_closed_loop"
    controller = pi_response(frequency_hz, kp_a_per_v, ki_a_per_vs)
    plant = impedance * inner_closed
    gain = controller * plant
    result = loop_margins(frequency_hz, gain)
    result["plant"] = plant
    result["loop_gain"] = gain
    result["inner_loop_model"] = inner_approximation
    return result


def bandwidth_separation_ratio(
    current_loop: dict[str, Any],
    voltage_loop: dict[str, Any],
) -> float | None:
    """电流环穿越频率 / 电压环穿越频率；任一缺失返回 ``None``。"""
    outer = voltage_loop.get("gain_crossover_hz")
    inner = current_loop.get("gain_crossover_hz")
    if outer is None or inner is None:
        return None
    if outer <= 0.0:
        return None
    return float(inner) / float(outer)

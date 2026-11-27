"""Buck 开环瞬态仿真入口。

本模块只负责把 :class:`circuits.buck_config.BuckParameters` 变成真实 ngspice
瞬态求解结果，并记录时间步长统计。稳态识别、验证与文件保存由脚本和分析层完成。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from circuits.buck import build_buck_from_parameters
from circuits.buck_config import BuckParameters
from circuits.validators import positive_number
from simulations.models import SimulationResult
from simulations.runner import SimulationRunner

#: 默认允许的最长扩展仿真时间（秒）。
DEFAULT_MAXIMUM_END_TIME_S = 20e-3


def time_step_statistics(
    time_s: Any,
    *,
    configured_max_step_s: float | None = None,
) -> dict[str, Any]:
    """统计实际时间步长，判断 ngspice 是否遵守最大步长约束。"""
    time = np.asarray(time_s, dtype=float)
    if time.ndim != 1 or time.size < 2:
        raise ValueError("time_s must be a 1D array with at least two samples")
    if not np.isfinite(time).all():
        raise ValueError("time_s contains NaN or Infinity")
    steps = np.diff(time)
    if np.any(steps <= 0):
        raise ValueError("time_s must be strictly increasing")

    statistics: dict[str, Any] = {
        "sample_count": int(time.size),
        "start_time_s": float(time[0]),
        "end_time_s": float(time[-1]),
        "min_step_s": float(steps.min()),
        "max_step_s": float(steps.max()),
        "mean_step_s": float(steps.mean()),
        "median_step_s": float(np.median(steps)),
        "nonuniform_sampling": bool(np.std(steps) > 1e-12 * max(1.0, float(steps.mean()))),
    }
    if configured_max_step_s is not None:
        configured = positive_number(configured_max_step_s, "configured_max_step_s")
        statistics["configured_max_step_s"] = configured
        statistics["max_step_respected"] = bool(statistics["max_step_s"] <= configured * 1.001)
    return statistics


def run_buck_transient(
    parameters: BuckParameters,
    *,
    end_time_s: float | None = None,
    step_time_s: float | None = None,
    max_step_time_s: float | None = None,
    temperature_c: float | None = None,
) -> SimulationResult:
    """执行一次真实 Buck 开环瞬态仿真。

    ``end_time_s`` / ``step_time_s`` / ``max_step_time_s`` 为实验覆盖值；
    覆盖后仍会经过 :class:`TransientConfig` 的完整校验。
    """
    if not isinstance(parameters, BuckParameters):
        raise ValueError("parameters must be BuckParameters")

    override: dict[str, float] = {}
    if end_time_s is not None:
        override["end_time_s"] = positive_number(end_time_s, "end_time_s")
    if step_time_s is not None:
        override["step_time_s"] = positive_number(step_time_s, "step_time_s")
    if max_step_time_s is not None:
        override["max_step_time_s"] = positive_number(max_step_time_s, "max_step_time_s")

    transient = replace(parameters.transient, **override) if override else parameters.transient
    transient.validate_for_switching(parameters.circuit.switching_frequency_hz)

    circuit = build_buck_from_parameters(parameters)
    simulation_temperature = (
        parameters.transient.temperature_c if temperature_c is None else float(temperature_c)
    )
    if simulation_temperature <= -273.15:
        raise ValueError("temperature_c must be above absolute zero")

    runner = SimulationRunner(temperature_c=simulation_temperature)
    result = runner.run_transient(
        circuit,
        transient.step_time_s,
        transient.end_time_s,
        0.0,
        max_time=transient.max_step_time_s,
        parameters={
            "input_voltage_v": parameters.circuit.input_voltage_v,
            "target_output_voltage_v": parameters.circuit.target_output_voltage_v,
            "rated_output_current_a": parameters.circuit.rated_output_current_a,
            "switching_frequency_hz": parameters.circuit.switching_frequency_hz,
            "duty_cycle": parameters.circuit.duty_cycle,
            "inductance_h": parameters.circuit.inductance_h,
            "capacitance_f": parameters.circuit.capacitance_f,
            "load_resistance_ohm": parameters.circuit.load_resistance_ohm,
            "pwm_low_voltage_v": parameters.pwm.low_voltage_v,
            "pwm_high_voltage_v": parameters.pwm.high_voltage_v,
            "pwm_pulse_width_s": parameters.pwm.pulse_width_s,
            "pwm_delay_s": parameters.pwm.delay_s,
            "step_time_s": transient.step_time_s,
            "max_step_time_s": transient.max_step_time_s,
            "end_time_s": transient.end_time_s,
        },
    )

    statistics = time_step_statistics(
        result.data["time_s"].to_numpy(),
        configured_max_step_s=transient.max_step_time_s,
    )
    result.metadata["time_step_statistics"] = statistics
    result.metadata["buck_parameters"] = parameters.to_dict()
    result.metadata["analysis_settings"] = {
        "requested_end_time_s": transient.end_time_s,
        "requested_step_time_s": transient.step_time_s,
        "requested_max_step_time_s": transient.max_step_time_s,
        "minimum_steps_per_period": parameters.circuit.period_s
        / transient.max_step_time_s,
        "simulation_temperature_c": simulation_temperature,
        "specification_type": "project_assumption",
        "model_type": parameters.model_type,
    }
    return result


def extended_end_time(
    current_end_s: float,
    *,
    maximum_end_s: float = DEFAULT_MAXIMUM_END_TIME_S,
) -> float | None:
    """返回下一次扩展仿真的结束时间；已达上限返回 ``None``。"""
    current = positive_number(current_end_s, "current_end_s")
    maximum = positive_number(maximum_end_s, "maximum_end_s")
    if current >= maximum:
        return None
    return float(min(maximum, current * 2.0))

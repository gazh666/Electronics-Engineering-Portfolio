"""闭环/开环 Buck 的平均状态空间模型求解器（非开关级）。

状态 ``x = [iL, vC, xI]``，其中 ``xI`` 为 PI 积分器状态（开环模式下不参与）。
模型假设：
- 理想平均 PWM：一个开关周期内用占空比代替开关动作；
- 保留电感 DCR、电容 ESR、MOSFET 导通电阻与二极管正向压降；
- 不使用 SPICE 开关器件，不产生纹波与开关尖峰。

因此本模块输出必须标记为 ``averaged_model``，不得与 ``closed_loop_runner``
的开关级 SPICE 波形混用或互相冒充。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from circuits.closed_loop_config import ClosedLoopConfig
from circuits.dynamic_load import CurrentStepLoad, ResistiveStepLoad
from circuits.validators import positive_number
from control.anti_windup import integral_increment
from control.averaged_buck import AveragedBuckParameters
from control.models import ControllerConfig
from control.pwm_modulator import effective_duty_sine
from control.soft_start import soft_start_reference

DATA_SOURCE_AVERAGED = "averaged_model"


def new_averaged_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"


def estimate_diode_forward_v(diode: Any, current_a: float) -> float:
    """由二极管参数估算正向压降：n·Vt·ln(I/IS) + I·RS。"""
    current = max(float(current_a), 1e-9)
    thermal = 0.025852
    return float(
        diode.ideality_factor * thermal * math.log(current / diode.saturation_current_a)
        + current * diode.series_resistance_ohm
    )


def estimate_mosfet_rds_on(mosfet: Any, gate_voltage_v: float) -> float:
    """Level-1 NMOS 线性区导通电阻倒数近似：KP·(W/L)·(Vgs−Vth)。"""
    overdrive = max(float(gate_voltage_v) - mosfet.threshold_voltage_v, 1e-6)
    width_over_length = mosfet.channel_width_m / mosfet.channel_length_m
    return float(1.0 / (mosfet.kp_a_per_v2 * width_over_length * overdrive))


def averaged_parameters_from_config(
    config: ClosedLoopConfig, *, load_current_a: float | None = None
) -> AveragedBuckParameters:
    """把闭环配置映射为平均模型参数（含文档化的器件近似）。"""
    ps = config.power_stage
    if isinstance(config.load, CurrentStepLoad):
        load_type = "constant_current"
        current = (
            config.load.initial_current_a
            if load_current_a is None
            else float(load_current_a)
        )
        resistance = ps.load_resistance_ohm
    elif isinstance(config.load, ResistiveStepLoad):
        load_type = "resistive"
        current = 0.0
        resistance = config.load.base_resistance_ohm
    else:
        load_type = "resistive"
        current = 0.0
        resistance = ps.load_resistance_ohm
    nominal_current = max(current, 2.0)
    return AveragedBuckParameters(
        vin_v=config.line.vin_initial_v,
        inductance_h=ps.inductor.inductance_h,
        capacitance_f=ps.capacitor.capacitance_f,
        load_resistance_ohm=resistance,
        dcr_ohm=ps.inductor.dcr_ohm,
        esr_ohm=ps.capacitor.esr_ohm,
        rds_on_ohm=estimate_mosfet_rds_on(ps.mosfet, ps.gate_driver.drive_voltage_v),
        diode_forward_v=estimate_diode_forward_v(ps.diode, nominal_current),
        load_type=load_type,
        load_current_a=current,
        switching_frequency_hz=ps.switching_frequency_hz,
    )


@dataclass
class AveragedRunResult:
    name: str
    run_id: str
    data: pd.DataFrame
    metadata: dict[str, Any]
    config_snapshot: dict[str, Any]
    duration_ms: float
    data_source: str = DATA_SOURCE_AVERAGED

    @property
    def point_count(self) -> int:
        return int(len(self.data))


def _load_config_at(config: ClosedLoopConfig) -> tuple[str, float, float]:
    """返回 (load_type, 初始负载电流, 初始等效电阻)。"""
    if isinstance(config.load, CurrentStepLoad):
        return "constant_current", config.load.initial_current_a, config.power_stage.load_resistance_ohm
    if isinstance(config.load, ResistiveStepLoad):
        return "resistive", 0.0, config.load.base_resistance_ohm
    return "resistive", 0.0, config.power_stage.load_resistance_ohm


def _load_runtime(config: ClosedLoopConfig, time_s: float, vout_v: float) -> tuple[float, float]:
    """返回 ``(实际负载电流, 等效电阻)``，与 SPICE 负载语义保持一致。"""
    if isinstance(config.load, CurrentStepLoad):
        command = config.load.current_at(time_s)
        scale = min(max(vout_v / config.load.compliance_voltage_v, 0.0), 1.0)
        return command * scale, config.power_stage.load_resistance_ohm
    if isinstance(config.load, ResistiveStepLoad):
        connected = (
            config.load.step_time_s <= time_s <= config.load.release_time_s
            if config.load.initial_connected
            else config.load.step_time_s <= time_s < config.load.release_time_s
        )
        resistance = config.load.equivalent_resistance(connected)
        return vout_v / resistance, resistance
    resistance = config.power_stage.load_resistance_ohm
    return vout_v / resistance, resistance


def run_averaged_closed_loop(
    config: ClosedLoopConfig,
    *,
    mode: str = "closed_loop",
    sample_dt_s: float = 1e-6,
    max_step_s: float = 2e-6,
    method: str = "RK45",
) -> AveragedRunResult:
    """求解闭环/开环平均模型。"""
    if not isinstance(config, ClosedLoopConfig):
        raise ValueError("config must be ClosedLoopConfig")
    if mode not in ("closed_loop", "open_loop"):
        raise ValueError("mode must be 'closed_loop' or 'open_loop'")
    dt = positive_number(sample_dt_s, "sample_dt_s")
    max_step = positive_number(max_step_s, "max_step_s")
    parameters = averaged_parameters_from_config(config)
    controller: ControllerConfig = config.controller
    load_type, load_current_initial, _ = _load_config_at(config)
    target = config.target_voltage_v
    dmin, dmax = controller.duty_min, controller.duty_max
    kp, ki, kaw = controller.kp, controller.ki, controller.tracking_gain
    frequency = config.switching_frequency_hz
    period = 1.0 / frequency
    soft = config.soft_start

    def reference(time_s: float) -> float:
        return soft_start_reference(
            time_s, target, soft.duration_s, soft.initial_reference_v, soft.enabled
        )

    def state_derivative(time_s: float, state: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
        il, vc, integral = float(state[0]), float(state[1]), float(state[2])
        vin = config.line.vin_at(time_s)
        vout_raw = vc + parameters.esr_ohm * il
        i_load_cmd, resistance = _load_runtime(config, time_s, vout_raw)
        if load_type == "resistive":
            vout = (vc + parameters.esr_ohm * il) / (
                1.0 + parameters.esr_ohm / resistance
            )
            i_load = vout / resistance
        else:
            i_load = i_load_cmd
            vout = vc + parameters.esr_ohm * (il - i_load)
        ref = reference(time_s)
        err = ref - vout
        ff = ref / max(vin, controller.vin_min_for_feedforward_v) if controller.feedforward_enabled else 0.0
        prop = kp * err
        raw = ff + prop + integral
        duty = min(max(raw, dmin), dmax)
        effective = effective_duty_sine(duty) if mode == "closed_loop" else config.open_loop_duty_cycle
        increment = (
            integral_increment(
                controller.anti_windup,
                ki=ki,
                error_v=err,
                dt_s=1.0,
                raw_duty=raw,
                limited_duty=duty,
                duty_min=dmin,
                duty_max=dmax,
                tracking_gain=kaw,
            )[0]
            if mode == "closed_loop"
            else 0.0
        )
        series = il * (effective * parameters.rds_on_ohm + parameters.dcr_ohm)
        di = (
            effective * vin
            - (1.0 - effective) * parameters.diode_forward_v
            - series
            - vout
        ) / parameters.inductance_h
        dvc = (il - i_load) / parameters.capacitance_f
        diagnostics = {
            "reference_v": ref,
            "error_v": err,
            "feedforward_duty": ff,
            "proportional_duty": prop,
            "raw_duty": raw,
            "duty_cmd": duty,
            "effective_duty": effective,
            "integral_state": integral,
            "vin_v": vin,
            "vout_v": vout,
            "iload_a": i_load,
            "saturated": float(abs(raw - duty) > 1e-12),
        }
        return np.array([di, dvc, increment], dtype=float), diagnostics

    def rhs(time_s: float, state: np.ndarray) -> np.ndarray:
        return state_derivative(time_s, state)[0]

    from scipy.integrate import solve_ivp

    times = np.arange(0.0, config.end_time_s + 0.5 * dt, dt)
    times = np.clip(times, 0.0, config.end_time_s)
    initial = np.array([0.0, 0.0, 0.0], dtype=float)
    started = time.perf_counter()
    solution = solve_ivp(
        rhs,
        (0.0, config.end_time_s),
        initial,
        method=method,
        t_eval=times,
        max_step=max_step,
        rtol=1e-7,
        atol=1e-9,
    )
    elapsed = time.perf_counter() - started
    if not solution.success:
        raise RuntimeError(f"averaged model integration failed: {solution.message}")

    rows: list[dict[str, float]] = []
    for index, time_s in enumerate(solution.t):
        state = solution.y[:, index]
        _, diagnostics = state_derivative(float(time_s), state)
        il, vc = float(state[0]), float(state[1])
        vout = diagnostics["vout_v"]
        delta = (
            (diagnostics["vin_v"] - vout)
            * diagnostics["effective_duty"]
            * period
            / parameters.inductance_h
        )
        valley = il - 0.5 * delta
        rows.append(
            {
                "time_s": float(time_s),
                "vout_v": vout,
                "vref_v": diagnostics["reference_v"],
                "verr_v": diagnostics["error_v"],
                "ff_v": diagnostics["feedforward_duty"],
                "prop_v": diagnostics["proportional_duty"],
                "integral_v": diagnostics["integral_state"],
                "raw_v": diagnostics["raw_duty"],
                "duty_cmd_v": diagnostics["duty_cmd"],
                "pwm_v": diagnostics["effective_duty"],
                "vin_v": diagnostics["vin_v"],
                "il_a": il,
                "vc_v": vc,
                "ic_a": il - diagnostics["iload_a"],
                "iin_a": diagnostics["effective_duty"] * il,
                "iload_a": diagnostics["iload_a"],
                "load_resistance_ohm": _load_runtime(config, float(time_s), vout)[1],
                "ccm": 1.0 if valley > 0.0 else 0.0,
                "inductor_ripple_a": delta,
                "inductor_valley_a": valley,
                "saturated": diagnostics["saturated"],
                "data_source": DATA_SOURCE_AVERAGED,
            }
        )
    data = pd.DataFrame(rows)
    metadata = {
        "name": config.name,
        "mode": mode,
        "data_source": DATA_SOURCE_AVERAGED,
        "model_type": "state_space_averaged",
        "states": ["inductor_current_a", "capacitor_voltage_v", "integral_state"],
        "modulator_model": "sine_carrier_average_mapping" if mode == "closed_loop" else "fixed_duty",
        "sample_dt_s": dt,
        "max_step_s": max_step,
        "method": method,
        "solver_success": bool(solution.success),
        "solver_message": str(solution.message),
        "wall_clock_s": elapsed,
        "duration_ms": 1000.0 * elapsed,
        "point_count": len(data),
        "parameters": parameters.to_dict(),
        "controller": controller.to_dict(),
        "soft_start": soft.to_dict(),
        "line": config.line.to_dict(),
        "load": config.load.to_dict() if config.load is not None else {"load_type": "resistive_fixed"},
        "not_a_switching_waveform": True,
        "notes": [
            "averaged PWM: no ripple, no switching spikes, no gate drive",
            "MOSFET on-resistance and diode forward drop are first-order estimates",
        ],
    }
    return AveragedRunResult(
        name=config.name,
        run_id=new_averaged_run_id(),
        data=data,
        metadata=metadata,
        config_snapshot=config.to_dict(),
        duration_ms=1000.0 * elapsed,
    )


def averaged_metrics(
    result: AveragedRunResult, *, period_s: float | None = None
) -> dict[str, Any]:
    """基本质量指标：末值、纹波（仅为模型数值，不是开关纹波）、CCM 比例、饱和比例。"""
    if not isinstance(result, AveragedRunResult):
        raise ValueError("result must be AveragedRunResult")
    data = result.data
    tail = data.iloc[-max(1, len(data) // 20):]
    return {
        "final_vout_v": float(data["vout_v"].iloc[-1]),
        "tail_mean_v": float(tail["vout_v"].mean()),
        "tail_min_v": float(tail["vout_v"].min()),
        "tail_max_v": float(tail["vout_v"].max()),
        "ccm_fraction": float(data["ccm"].mean()),
        "saturation_fraction": float(data["saturated"].mean()),
        "peak_inductor_current_a": float(data["il_a"].max()),
        "peak_input_current_a": float(data["iin_a"].max()),
        "final_duty_cmd": float(data["duty_cmd_v"].iloc[-1]),
        "final_effective_duty": float(data["pwm_v"].iloc[-1]),
        "data_source": result.data_source,
        "model_type": "state_space_averaged",
        "note": "waveform is an averaged model, not a switching SPICE waveform",
    }


__all__ = [
    "AveragedRunResult",
    "DATA_SOURCE_AVERAGED",
    "averaged_metrics",
    "averaged_parameters_from_config",
    "estimate_diode_forward_v",
    "estimate_mosfet_rds_on",
    "new_averaged_run_id",
    "run_averaged_closed_loop",
]

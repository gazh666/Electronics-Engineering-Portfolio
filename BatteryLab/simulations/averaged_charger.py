"""平均（状态空间）CC-CV 充电模型：用于整定、趋势预演与开关级对照。

层次声明：本模块是**平均模型**，不是开关级验证。

- 不产生 PWM 纹波，因此不能用于验证纹波、逐周期限流、DCM 边界；
- 控制律与 ``charging/pi_controller.py``、``circuits/charger_spice_controller.py``
  完全一致（同一组 kp/ki/kaw、条件积分 + 反计算、滤波前馈、软启动）；
- 状态方程：Buck 平均模型（含 DCR、ESR、Ron、二极管压降）+ 3S 一阶 RC 电池，
  电池参数来自第三阶段冻结辨识结果。

结论只能表述为"平均模型下……"，不得与真实 ngspice 波形混为同一层证据。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from analysis.cc_cv_transition import detect_cc_to_cv_transition, phase_charge_totals_ah
from analysis.charging_energy import calculate_charging_energy
from analysis.charging_efficiency import calculate_charger_efficiency
from battery_models.states import update_polarization_voltage
from charging.battery_adapter import load_identified_battery_bundle, soc_validity
from charging.config import ChargerConfig, ControllerConfig
from charging.pi_controller import PIController
from charging.soft_start import CurrentSoftStart


class AveragedChargerError(ValueError):
    """平均模型输入非法。"""


@dataclass(frozen=True)
class AveragedChargerParameters:
    series_cells: int
    capacity_ah: float
    vin_v: float
    switching_frequency_hz: float
    inductance_h: float
    capacitance_f: float
    inductor_dcr_ohm: float
    capacitor_esr_ohm: float
    diode_drop_v: float
    mosfet_ron_ohm: float
    path_resistance_ohm: float
    current_target_a: float
    voltage_target_v: float
    termination_current_a: float
    termination_hold_s: float
    maximum_charge_time_s: float
    soft_start_time_s: float
    voltage_kp: float
    voltage_ki: float
    voltage_kaw: float
    current_kp: float
    current_ki: float
    current_kaw: float
    duty_min: float
    duty_max: float
    feedforward_filter_time_s: float = 1e-3

    @classmethod
    def from_configs(
        cls, charger: ChargerConfig, controller: ControllerConfig
    ) -> "AveragedChargerParameters":
        return cls(
            series_cells=charger.battery.series_cells,
            capacity_ah=charger.battery.reference_capacity_ah,
            vin_v=charger.power_stage.input_voltage_v,
            switching_frequency_hz=charger.power_stage.switching_frequency_hz,
            inductance_h=charger.power_stage.inductance_h,
            capacitance_f=charger.power_stage.capacitance_f,
            inductor_dcr_ohm=charger.power_stage.inductor_dcr_ohm,
            capacitor_esr_ohm=charger.power_stage.capacitor_esr_ohm,
            diode_drop_v=charger.power_stage.diode_forward_voltage_estimate_v,
            mosfet_ron_ohm=charger.power_stage.mosfet_rds_on_target_ohm,
            path_resistance_ohm=charger.power_stage.path_resistance_ohm,
            current_target_a=charger.charging.constant_current_a,
            voltage_target_v=charger.charging.constant_voltage_v,
            termination_current_a=charger.charging.termination_current_a,
            termination_hold_s=charger.charging.termination_hold_time_s,
            maximum_charge_time_s=charger.charging.maximum_charge_time_s,
            soft_start_time_s=charger.charging.soft_start_time_s,
            voltage_kp=controller.voltage_loop.kp,
            voltage_ki=controller.voltage_loop.ki,
            voltage_kaw=controller.voltage_loop.kaw,
            current_kp=controller.current_loop.kp,
            current_ki=controller.current_loop.ki,
            current_kaw=controller.current_loop.kaw,
            duty_min=controller.duty_min,
            duty_max=controller.duty_max,
        )

    def validate(self) -> "AveragedChargerParameters":
        positive = (
            "series_cells",
            "capacity_ah",
            "vin_v",
            "switching_frequency_hz",
            "inductance_h",
            "capacitance_f",
            "current_target_a",
            "voltage_target_v",
            "termination_hold_s",
            "maximum_charge_time_s",
            "feedforward_filter_time_s",
        )
        for name in positive:
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise AveragedChargerError(f"{name} 必须为正")
        for name in (
            "inductor_dcr_ohm",
            "capacitor_esr_ohm",
            "diode_drop_v",
            "mosfet_ron_ohm",
            "path_resistance_ohm",
            "soft_start_time_s",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise AveragedChargerError(f"{name} 非法")
        if not 0.0 <= self.duty_min < self.duty_max < 1.0:
            raise AveragedChargerError("占空比范围非法")
        if self.voltage_target_v / self.vin_v > self.duty_max:
            raise AveragedChargerError("恒压目标所需占空比超过 duty_max")
        if self.termination_current_a >= self.current_target_a:
            raise AveragedChargerError("终止电流必须低于恒流值")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class AveragedChargeResult:
    time_s: np.ndarray
    pack_voltage_v: np.ndarray
    charging_current_a: np.ndarray
    input_voltage_v: np.ndarray
    input_current_a: np.ndarray
    duty: np.ndarray
    current_reference_a: np.ndarray
    soc: np.ndarray
    cell_voltage_v: np.ndarray
    state: str
    termination_reason: str
    metrics: dict[str, Any]

    def to_columns(self) -> dict[str, np.ndarray]:
        return {
            "time_s": self.time_s,
            "battery_pack_voltage_v": self.pack_voltage_v,
            "charging_current_a": self.charging_current_a,
            "input_voltage_v": self.input_voltage_v,
            "input_current_a": self.input_current_a,
            "duty": self.duty,
            "current_reference_a": self.current_reference_a,
            "soc": self.soc,
            "cell_voltage_v": self.cell_voltage_v,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "layers": "averaged_simulation",
            "points": int(self.time_s.size),
            "duration_s": float(self.time_s[-1] - self.time_s[0]),
            "final_pack_voltage_v": float(self.pack_voltage_v[-1]),
            "final_charging_current_a": float(self.charging_current_a[-1]),
            "final_soc": float(self.soc[-1]),
            "state": self.state,
            "termination_reason": self.termination_reason,
            **self.metrics,
        }


def _battery_aggregate(model_id: str, series_cells: int) -> dict[str, Any]:
    bundle = load_identified_battery_bundle(model_id)
    parameters = bundle["parameters"]
    return {
        "ocv_model": bundle["ocv_model"],
        "r0_ohm": float(parameters.r0_ohm),
        "r1_ohm": float(parameters.r1_ohm),
        "c1_f": float(parameters.c1_f),
        "soc_min": float(bundle["identified_soc_min"]),
        "soc_max": float(bundle["identified_soc_max"]),
        "model_id": str(bundle["model_id"]),
        "series_cells": int(series_cells),
    }


def _plain_regulation_metrics(
    time_s: np.ndarray,
    values: np.ndarray,
    target: float,
    window_s: float | None,
    unit: str,
) -> dict[str, float | int | None]:
    start = float(time_s[0]) if window_s is None else float(time_s[-1] - window_s)
    mask = time_s >= start
    if int(mask.sum()) < 3:
        raise AveragedChargerError("统计窗口内采样点不足")
    window = values[mask]
    error = window - target
    return {
        f"mean_{unit}": float(window.mean()),
        f"mean_error_{unit}": float(error.mean()),
        f"mae_{unit}": float(np.abs(error).mean()),
        f"peak_error_{unit}": float(np.abs(error).max()),
        "samples": int(window.size),
        "window_s": None if window_s is None else float(window_s),
    }


def simulate_averaged_charge(
    parameters: AveragedChargerParameters,
    *,
    initial_soc: float,
    duration_s: float,
    model_id: str = "calce_sp2_25c_inr18650_20r_first_order_v1",
    step_s: float = 2e-5,
    bms_charge_allowed: bool = True,
    stop_at_termination: bool = True,
) -> AveragedChargeResult:
    """平均模型 CC-CV 充电。

    ``step_s`` 是平均模型的数值积分步长，不代表开关周期；
    平均模型没有 PWM 纹波，不能据此判断开关级稳定性。
    """
    parameters.validate()
    if not 0.0 < initial_soc < 1.0:
        raise AveragedChargerError("初始 SOC 必须位于 (0, 1)")
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        raise AveragedChargerError("仿真时长必须为正")
    if not math.isfinite(step_s) or step_s <= 0.0:
        raise AveragedChargerError("积分步长必须为正")
    # 平均模型只需分辨电流环带宽（约 720 Hz），2e-5 s 已足够；过大会失真。
    if step_s > 2e-4:
        raise AveragedChargerError("平均模型步长过大，无法分辨电流环带宽")

    battery = _battery_aggregate(model_id, parameters.series_cells)
    ocv_model = battery["ocv_model"]
    n = parameters.series_cells
    r0_pack = n * battery["r0_ohm"]
    r1_pack = n * battery["r1_ohm"]
    c1_pack = battery["c1_f"] / n

    cap = parameters.capacity_ah
    total_seconds = min(duration_s, parameters.maximum_charge_time_s)
    steps = int(math.ceil(total_seconds / step_s))

    voltage_pi = PIController(parameters.voltage_kp, parameters.voltage_ki, parameters.voltage_kaw)
    current_pi = PIController(parameters.current_kp, parameters.current_ki, parameters.current_kaw)
    soft_start = CurrentSoftStart(parameters.soft_start_time_s)

    soc = float(initial_soc)
    polarization_v = 0.0
    inductor_current_a = 0.0
    capacitor_voltage_v = n * float(ocv_model.voltage(soc))
    filtered_output_v = capacitor_voltage_v
    battery_current_a = 0.0
    termination_since_s: float | None = None
    state = "CC"
    termination_reason = "DURATION_REACHED"

    time_values: list[float] = []
    pack_values: list[float] = []
    current_values: list[float] = []
    input_current_values: list[float] = []
    duty_values: list[float] = []
    reference_values: list[float] = []
    soc_values: list[float] = []
    cell_values: list[float] = []

    duty = 0.0
    current_reference = 0.0
    for index in range(steps + 1):
        elapsed = index * step_s
        ocv_cell = float(ocv_model.voltage(soc))
        ocv_pack = n * ocv_cell
        # 输出节点电压含 ESR 压降；电池支路与输出电容并联。
        denominator = r0_pack + parameters.path_resistance_ohm + parameters.capacitor_esr_ohm
        battery_current_a = (
            capacitor_voltage_v
            + parameters.capacitor_esr_ohm * inductor_current_a
            - (ocv_pack + polarization_v)
        ) / denominator
        output_voltage_v = capacitor_voltage_v + parameters.capacitor_esr_ohm * (
            inductor_current_a - battery_current_a
        )
        pack_voltage_v = output_voltage_v - parameters.path_resistance_ohm * battery_current_a

        # 记录的是区间 [t, t+dt) 实际施加的占空比与电流指令（零阶保持）。
        time_values.append(elapsed)
        pack_values.append(pack_voltage_v)
        current_values.append(battery_current_a)
        input_current_values.append(duty * inductor_current_a)
        duty_values.append(duty)
        reference_values.append(current_reference)
        soc_values.append(soc)
        cell_values.append(pack_voltage_v / n)

        if elapsed >= total_seconds - 1e-15:
            if total_seconds >= parameters.maximum_charge_time_s:
                termination_reason = "MAXIMUM_CHARGE_TIME"
                state = "TIMEOUT"
            break

        if not bms_charge_allowed:
            state = "FAULT"
            termination_reason = "BMS_CHARGE_INHIBITED"
            break

        # 电压环以真实电池端电压（pack 节点）为反馈，前馈用滤波后的输出节点。
        filtered_output_v += step_s * (output_voltage_v - filtered_output_v) / parameters.feedforward_filter_time_s
        voltage_error = parameters.voltage_target_v - pack_voltage_v
        current_limit = soft_start.step(parameters.current_target_a, step_s)
        current_reference = voltage_pi.step(
            error=voltage_error, dt_s=step_s, lower=0.0, upper=current_limit
        )
        duty_feedforward = (filtered_output_v + parameters.diode_drop_v) / (
            parameters.vin_v + parameters.diode_drop_v
        )
        duty_feedforward = min(max(duty_feedforward, parameters.duty_min), parameters.duty_max)
        duty = current_pi.step(
            error=current_reference - inductor_current_a,
            dt_s=step_s,
            lower=parameters.duty_min,
            upper=parameters.duty_max,
            feedforward=duty_feedforward,
        )

        # 平均 Buck 状态方程。
        switch_voltage = duty * (parameters.vin_v - parameters.mosfet_ron_ohm * inductor_current_a)
        diode_voltage = (1.0 - duty) * parameters.diode_drop_v
        di_dt = (
            switch_voltage
            - diode_voltage
            - output_voltage_v
            - parameters.inductor_dcr_ohm * inductor_current_a
        ) / parameters.inductance_h
        inductor_current_a += di_dt * step_s
        capacitor_voltage_v += (inductor_current_a - battery_current_a) * step_s / parameters.capacitance_f

        # 电池状态：SOC 与极化电压（充电为正）。
        soc += battery_current_a * step_s / (3600.0 * cap)
        soc = min(max(soc, 0.0), 1.0)
        polarization_v = update_polarization_voltage(
            polarization_v,
            battery_current_a,
            r1_pack,
            c1_pack,
            step_s,
        )

        # 状态标签：仅表示电压是否到达恒压区，仍需真实电流确认。
        near_cv = abs(pack_voltage_v - parameters.voltage_target_v) <= 0.02
        if near_cv and current_reference < parameters.current_target_a * 0.999:
            state = "CV"
        elif soft_start.fraction < 1.0:
            state = "SOFT_START"
        else:
            state = "CC"

        if stop_at_termination and state == "CV" and battery_current_a <= parameters.termination_current_a:
            if termination_since_s is None:
                termination_since_s = elapsed
            elif elapsed - termination_since_s >= parameters.termination_hold_s:
                state = "COMPLETE"
                termination_reason = "TERMINATION_CURRENT"
                break
        else:
            termination_since_s = None

        if soc >= 0.999:
            state = "COMPLETE"
            termination_reason = "SOC_UPPER_LIMIT"
            break

    time_array = np.asarray(time_values, dtype=float)
    pack_array = np.asarray(pack_values, dtype=float)
    current_array = np.asarray(current_values, dtype=float)
    input_voltage_array = np.full(time_array.shape, parameters.vin_v, dtype=float)
    input_current_array = np.asarray(input_current_values, dtype=float)
    duty_array = np.asarray(duty_values, dtype=float)
    reference_array = np.asarray(reference_values, dtype=float)
    soc_array = np.asarray(soc_values, dtype=float)

    metrics = _metrics(
        parameters,
        battery,
        time_array,
        pack_array,
        current_array,
        input_voltage_array,
        input_current_array,
        soc_array,
        state,
    )
    return AveragedChargeResult(
        time_s=time_array,
        pack_voltage_v=pack_array,
        charging_current_a=current_array,
        input_voltage_v=input_voltage_array,
        input_current_a=input_current_array,
        duty=duty_array,
        current_reference_a=reference_array,
        soc=soc_array,
        cell_voltage_v=pack_array / n,
        state=state,
        termination_reason=termination_reason,
        metrics=metrics,
    )


def _metrics(
    parameters: AveragedChargerParameters,
    battery: dict[str, Any],
    time_array: np.ndarray,
    pack_array: np.ndarray,
    current_array: np.ndarray,
    input_voltage_array: np.ndarray,
    input_current_array: np.ndarray,
    soc_array: np.ndarray,
    state: str,
) -> dict[str, Any]:
    if time_array.size < 2:
        # BMS 许可一开始就为 False 时只会记录初始点；此时没有可供统计的动态过程。
        return {
            "method": "averaged_simulation",
            "initial_soc": float(soc_array[0]),
            "final_soc": float(soc_array[-1]),
            "soc_validity": soc_validity(
                float(soc_array[-1]), battery["soc_min"], battery["soc_max"]
            ),
            "reached_cv": False,
            "cc_to_cv_time_s": None,
            "cc_mean_current_a": None,
            "cc_mean_error_a": None,
            "cc_mae_a": None,
            "cv_mean_voltage_v": None,
            "cv_mean_error_v": None,
            "cv_mae_v": None,
            "voltage_overshoot_v": 0.0,
            "final_current_a": float(current_array[-1]),
            "charge_cc_ah": 0.0,
            "charge_cv_ah": 0.0,
            "charge_total_ah": 0.0,
            "battery_energy_wh": 0.0,
            "input_energy_wh": 0.0,
            "energy_efficiency_percent": None,
            "instantaneous_efficiency_percent": None,
            "state": state,
            "note": "记录点不足两点，仅报告初始状态",
        }
    transition = detect_cc_to_cv_transition(
        time_array, pack_array, parameters.voltage_target_v, 0.02, hold_time_s=1e-3
    )
    window_s = min(1e-3, float(time_array[-1] - time_array[0]))
    cc_reference_end = float(time_array[-1]) if transition is None else float(transition)
    if cc_reference_end > 5e-3:
        mask = (time_array >= cc_reference_end - 1e-3) & (time_array <= cc_reference_end)
        cc_current = current_array[mask]
        cc_metrics = {
            "mean_a": float(cc_current.mean()),
            "mean_error_a": float(cc_current.mean() - parameters.current_target_a),
            "mae_a": float(np.abs(cc_current - parameters.current_target_a).mean()),
            "samples": int(cc_current.size),
        }
    else:
        cc_metrics = {"mean_a": None, "mean_error_a": None, "mae_a": None, "samples": 0}

    if transition is None:
        cv_metrics = {"mean_v": None, "mean_error_v": None, "mae_v": None, "samples": 0}
    else:
        mask = time_array >= transition
        cv_metrics = _plain_regulation_metrics(
            time_array[mask], pack_array[mask], parameters.voltage_target_v, window_s, "v"
        )

    overshoot = max(0.0, float(pack_array.max()) - parameters.voltage_target_v)
    phase_charge = phase_charge_totals_ah(
        time_array, pack_array, current_array, parameters.voltage_target_v, 0.02
    )
    energy = calculate_charging_energy(
        time_array, pack_array, current_array, input_voltage_array, input_current_array
    )
    efficiency = calculate_charger_efficiency(
        time_array, input_voltage_array, input_current_array, pack_array, current_array
    )
    validity = soc_validity(
        float(soc_array[-1]), battery["soc_min"], battery["soc_max"]
    )
    return {
        "method": "averaged_simulation",
        "initial_soc": float(soc_array[0]),
        "final_soc": float(soc_array[-1]),
        "soc_validity": validity,
        "reached_cv": transition is not None,
        "cc_to_cv_time_s": None if transition is None else float(transition),
        "cc_mean_current_a": cc_metrics["mean_a"],
        "cc_mean_error_a": cc_metrics["mean_error_a"],
        "cc_mae_a": cc_metrics["mae_a"],
        "cv_mean_voltage_v": cv_metrics["mean_v"],
        "cv_mean_error_v": cv_metrics["mean_error_v"],
        "cv_mae_v": cv_metrics["mae_v"],
        "voltage_overshoot_v": overshoot,
        "final_current_a": float(current_array[-1]),
        "charge_cc_ah": float(phase_charge["cc_charge_ah"]),
        "charge_cv_ah": float(phase_charge["cv_charge_ah"]),
        "charge_total_ah": float(phase_charge["total_charge_ah"]),
        "battery_energy_wh": float(energy.battery_energy_wh),
        "input_energy_wh": None if energy.input_energy_wh is None else float(energy.input_energy_wh),
        "energy_efficiency_percent": (
            None if energy.energy_efficiency_percent is None else float(energy.energy_efficiency_percent)
        ),
        "instantaneous_efficiency_percent": float(efficiency["power_stage_efficiency_percent"]),
        "state": state,
    }


def compare_with_switching(
    averaged: AveragedChargeResult,
    switching_summary: dict[str, Any],
) -> dict[str, Any]:
    """平均模型与开关级结果的对照差值（仅同一初始条件下的同向比较）。"""
    if not isinstance(switching_summary, dict):
        raise AveragedChargerError("开关级汇总必须是映射")
    pairs = {
        "final_pack_voltage_v": (float(averaged.pack_voltage_v[-1]), switching_summary.get("final_pack_voltage_v")),
        "final_charging_current_a": (
            float(averaged.charging_current_a[-1]),
            switching_summary.get("final_charging_current_a"),
        ),
    }
    differences: dict[str, Any] = {}
    for name, (model_value, reference) in pairs.items():
        if reference is None:
            differences[name] = {"averaged": model_value, "switching": None, "difference": None}
            continue
        reference_value = float(reference)
        differences[name] = {
            "averaged": model_value,
            "switching": reference_value,
            "difference": model_value - reference_value,
        }
    return differences


def run_default_cases() -> list[dict[str, Any]]:
    """C01–C03 的平均模型对照（仅用于趋势与整定，不作为开关级证据）。"""
    from charging.config import load_charger_config, load_controller_config

    charger = load_charger_config()
    controller = load_controller_config()
    parameters = AveragedChargerParameters.from_configs(charger, controller).validate()
    rows: list[dict[str, Any]] = []
    for case_id, initial_soc, duration in (
        ("AVG_C01", 0.30, 0.05),
        ("AVG_C02", 0.62, 0.05),
        ("AVG_C03", 0.50, 0.08),
    ):
        result = simulate_averaged_charge(
            parameters,
            initial_soc=initial_soc,
            duration_s=duration,
            stop_at_termination=False,
        )
        rows.append({"case": case_id, **result.summary()})
    return rows


def numerical_assumptions(parameters: AveragedChargerParameters, step_s: float) -> dict[str, Any]:
    return {
        "layers": "averaged_simulation",
        "integrator": "explicit_euler_average_state_space",
        "step_s": float(step_s),
        "excluded_effects": ["pwm_ripple", "cycle_by_cycle_current_limit", "dcm_boundary"],
        "control_law": "same_pi_conditional_integral_as_spice_netlist",
        "parameters": parameters.to_dict(),
    }

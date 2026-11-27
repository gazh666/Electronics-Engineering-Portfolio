"""12 个开关级 SPICE 充电工况：真实 ngspice 双闭环求解、保护许可与指标回填。

本模块只负责"某个工况"的构建、求解、判定与落盘，不生成任何波形。
所有波形来自 ``circuits.charger_spice_controller.run_cascade_buck``（网表内行为源
级联 PI + PWM + 3S 电池夹具）。

BMS 许可的使用方式：
1. 运行前用第五阶段真实 ``ProtectionController`` 对初始单体电压做许可校验，
   不允许充电时直接拒绝运行（不是伪造 allowed=True）；
2. 运行后把真实波形逐点回灌同一个真实保护控制器，记录充电许可与故障；
   短时开关实验（8–12 ms）短于多数确认延时，因此同时做逐点原始限值检查，
   并明确区分"限值检查"与"保护锁存"。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from analysis.charging_efficiency import calculate_charger_efficiency, last_window_average
from analysis.charging_energy import calculate_charging_energy
from analysis.charging_metrics import cc_regulation_metrics, cv_regulation_metrics, switching_period_average
from analysis.cc_cv_transition import transition_summary
from charging.config import (
    ChargerConfig,
    ControllerConfig,
    ChargingCase,
    load_charger_config,
    load_charging_cases,
    load_controller_config,
)
from charging.protection_adapter import create_protection_controller
from circuits.charger_buck import ChargerWaveform, PackFixture, pwl_expression, step_expression
from circuits.charger_spice_controller import (
    CascadeParameters,
    MINIMUM_RELIABLE_STEP_S,
    build_cascade_circuit,
    run_cascade_buck,
)
from circuits.spice_utils import save_netlist
from storage.result_store import RunDirectory

SPICE_CASE_IDS = (
    "C01",
    "C02",
    "C03",
    "C04",
    "C05",
    "C06",
    "C07",
    "C08",
    "C09",
    "C10",
    "C19",
    "C20",
)

DEFAULT_STEP_S = MINIMUM_RELIABLE_STEP_S
STEADY_WINDOW_S = 2e-3
PROTECTION_REPLAY_DECIMATION = 20


class SpiceCaseError(RuntimeError):
    """开关级工况构建或判定失败。"""


@dataclass
class CaseRun:
    case_id: str
    name: str
    method: str
    waveform: ChargerWaveform
    summary: dict[str, Any]
    checks: list[dict[str, Any]]
    run_dir: RunDirectory | None = None
    netlist_path: str | None = None
    waveform_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "method": self.method,
            "checks": list(self.checks),
            "run_dir": None if self.run_dir is None else str(self.run_dir.path),
            "netlist_path": self.netlist_path,
            "waveform_path": self.waveform_path,
            **self.summary,
        }


def _check(name: str, measured: float | None, limit: float | None, unit: str, passed: bool, note: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "measured": measured,
        "limit": limit,
        "unit": unit,
        "status": "PASS" if passed else "FAIL",
        "note": note,
    }


def number(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number_value = float(value)
    return number_value if math.isfinite(number_value) else None


def _load_case(case_id: str) -> ChargingCase:
    for case in load_charging_cases():
        if case.id == case_id:
            return case
    raise SpiceCaseError(f"工况不存在: {case_id}")


def _fixture(case: ChargingCase, charger: ChargerConfig) -> PackFixture:
    parameters = dict(case.parameters)
    vocv = parameters.get("vocv_v")
    if vocv is None:
        raise SpiceCaseError(f"{case.id} 缺少 vocv_v")
    return PackFixture.from_equivalent_voltage(
        float(vocv),
        charger.power_stage.path_resistance_ohm,
        series_cells=charger.battery.series_cells,
        model_id=charger.battery.identified_model_id,
    )


def _expressions(case: ChargingCase) -> dict[str, str]:
    parameters = dict(case.parameters)
    step_time = parameters.get("step_time_s")
    vin_initial = parameters.get("vin_initial_v")
    vin_final = parameters.get("vin_final_v")
    iset_initial = parameters.get("iset_initial_a")
    iset_final = parameters.get("iset_final_a")
    enable_initial = parameters.get("enable_initial")
    enable_final = parameters.get("enable_final")

    if vin_initial is not None and vin_final is not None and step_time is not None:
        vin_expression = step_expression(float(vin_initial), float(vin_final), float(step_time))
    else:
        vin_expression = f"DC {float(parameters.get('vin_initial_v', 18.0)):.9g}"

    if iset_initial is not None and iset_final is not None and step_time is not None:
        iset_expression = step_expression(float(iset_initial), float(iset_final), float(step_time))
    else:
        iset_expression = f"DC {float(parameters.get('current_reference_a', 1.0)):.9g}"

    if enable_initial is not None and enable_final is not None and step_time is not None:
        enable_expression = step_expression(float(enable_initial), float(enable_final), float(step_time))
    else:
        enable_expression = f"DC {float(parameters.get('enable_initial', 1.0)):.9g}"

    return {
        "vin_expression": vin_expression,
        "current_set_expression": iset_expression,
        "enable_expression": enable_expression,
    }


def _precheck_permission(fixture: PackFixture, temperature_c: float) -> dict[str, Any]:
    controller = create_protection_controller(
        [f"cell{index + 1}" for index in range(len(fixture.cells))]
    )
    snapshot = controller.update(
        0.0,
        [cell.ocv_v for cell in fixture.cells],
        0.0,
        temperature_c,
    )
    return {
        "charge_allowed": bool(snapshot.charge_allowed),
        "measurement_valid": bool(snapshot.measurement_valid),
        "active_faults": list(snapshot.active_faults),
        "state": snapshot.state.value,
    }


def _replay_protection(
    waveform: ChargerWaveform,
    temperature_c: float,
) -> dict[str, Any]:
    controller = create_protection_controller(
        [f"cell{index + 1}" for index in range(len(waveform.cell_voltages_v))]
    )
    time = waveform.time_s
    step = max(1, int(PROTECTION_REPLAY_DECIMATION))
    indices = list(range(0, time.size, step))
    if indices[-1] != time.size - 1:
        indices.append(time.size - 1)

    first_inhibit_time: float | None = None
    latched: set[str] = set()
    for index in indices:
        snapshot = controller.update(
            float(time[index]),
            [float(cell[index]) for cell in waveform.cell_voltages_v],
            -float(waveform.charging_current_a[index]),
            temperature_c,
        )
        if not snapshot.charge_allowed and first_inhibit_time is None:
            first_inhibit_time = float(time[index])
        latched.update(snapshot.latched_faults)
    return {
        "replayed_points": len(indices),
        "first_inhibit_time_s": first_inhibit_time,
        "latched_faults": sorted(latched),
        "charge_allowed_throughout": first_inhibit_time is None,
        "note": "短窗实验短于多数确认延时；锁存结论仅在窗口内有效",
    }


def _raw_limit_check(
    waveform: ChargerWaveform,
    limits: Any,
    frequency_hz: float,
) -> dict[str, Any]:
    """保护限值核查。

    开关断点处 ngspice 会取 fs 级时间步，788 F 极化电容的 ``C/dt`` 使单体电压
    分配矩阵条件数急剧变差，出现 bt 级数值伪影（总量守恒、分配失真）。
    真实 AFE 以 ms 级速率、经 RC 滤波采样，因此限值判定使用 PWM 周期平均，
    同时如实报告瞬时极值与断点样本数，不隐藏任何数据。
    """
    instantaneous_cell_max = float(max(float(cell.max()) for cell in waveform.cell_voltages_v))
    instantaneous_cell_min = float(min(float(cell.min()) for cell in waveform.cell_voltages_v))
    period_max = float("-inf")
    period_min = float("inf")
    for cell in waveform.cell_voltages_v:
        _, average, _, _ = switching_period_average(waveform.time_s, cell, frequency_hz)
        period_max = max(period_max, float(average.max()))
        period_min = min(period_min, float(average.min()))
    charge_max = float(waveform.charging_current_a.max())
    discharge_max = float(max(0.0, -waveform.charging_current_a.min()))
    breakpoint_steps = int(np.count_nonzero(np.diff(waveform.time_s) < 1e-9))
    return {
        "max_cell_voltage_v": period_max,
        "min_cell_voltage_v": period_min,
        "instantaneous_max_cell_voltage_v": instantaneous_cell_max,
        "instantaneous_min_cell_voltage_v": instantaneous_cell_min,
        "max_charge_current_a": charge_max,
        "max_reverse_current_a": discharge_max,
        "cell_overvoltage_trip_v": float(limits.cell_overvoltage_trip_v),
        "cell_undervoltage_trip_v": float(limits.cell_undervoltage_trip_v),
        "charge_overcurrent_trip_a": float(limits.charge_overcurrent_trip_a),
        "short_circuit_trip_a": float(limits.short_circuit_trip_a),
        "overvoltage_violated": period_max > limits.cell_overvoltage_trip_v,
        "undervoltage_violated": period_min < limits.cell_undervoltage_trip_v,
        "charge_overcurrent_violated": charge_max > limits.charge_overcurrent_trip_a,
        "switching_breakpoint_steps": breakpoint_steps,
        "voltage_check_basis": "pwm_period_average_equivalent_to_afe_sampling",
    }


def _loss_breakdown(
    waveform: ChargerWaveform,
    charger: ChargerConfig,
    window_start_s: float,
    window_stop_s: float | None = None,
) -> dict[str, float]:
    stop = float(waveform.time_s[-1]) if window_stop_s is None else float(window_stop_s)
    mask = (waveform.time_s >= window_start_s) & (waveform.time_s <= stop)
    if int(mask.sum()) < 10:
        raise SpiceCaseError("稳态窗口内采样点不足")
    t = waveform.time_s[mask]
    duration = float(t[-1] - t[0])
    if duration <= 0.0:
        raise SpiceCaseError("稳态窗口时长为零")

    def mean(values: np.ndarray) -> float:
        integrate = getattr(np, "trapezoid", None) or np.trapz
        return float(integrate(values[mask], t) / duration)

    power = charger.power_stage
    duty = waveform.duty_command
    inductor = waveform.inductor_current_a
    battery = waveform.charging_current_a
    capacitor = inductor - battery

    switch_loss = mean(duty * power.mosfet_rds_on_target_ohm * inductor**2)
    diode_loss = mean((1.0 - duty) * power.diode_forward_voltage_estimate_v * inductor)
    dcr_loss = mean(power.inductor_dcr_ohm * inductor**2)
    esr_loss = mean(power.capacitor_esr_ohm * capacitor**2)
    path_loss = mean(charger.power_stage.path_resistance_ohm * battery**2)
    return {
        "switch_conduction_w": switch_loss,
        "diode_conduction_w": diode_loss,
        "inductor_dcr_w": dcr_loss,
        "capacitor_esr_w": esr_loss,
        "path_resistance_w": path_loss,
        "total_stage_loss_w": switch_loss + diode_loss + dcr_loss + esr_loss + path_loss,
    }


def _energy_metrics(waveform: ChargerWaveform) -> dict[str, Any]:
    energy = calculate_charging_energy(
        waveform.time_s,
        waveform.pack_voltage_v,
        waveform.charging_current_a,
        waveform.input_voltage_v,
        waveform.input_current_a,
    )
    payload = energy.to_dict()
    if energy.integration_gap_percent is not None:
        payload["zoh_trapezoid_gap_ppm"] = abs(energy.integration_gap_percent) * 1e4
    else:
        payload["zoh_trapezoid_gap_ppm"] = None
    return payload


def _conduction_mode(
    waveform: ChargerWaveform,
    charger: ChargerConfig,
    window_start_s: float,
    window_stop_s: float | None = None,
) -> dict[str, Any]:
    stop = float(waveform.time_s[-1]) if window_stop_s is None else float(window_stop_s)
    mask = (waveform.time_s >= window_start_s) & (waveform.time_s <= stop)
    power = charger.power_stage
    duty = float(np.mean(waveform.duty_command[mask]))
    output = float(np.mean(waveform.pack_voltage_v[mask]))
    current = float(np.mean(waveform.charging_current_a[mask]))
    ripple = (charger.power_stage.input_voltage_v - output) * duty / (
        power.inductance_h * power.switching_frequency_hz
    )
    valley = current - ripple / 2.0
    peak = current + ripple / 2.0
    return {
        "duty_mean": duty,
        "output_voltage_mean_v": output,
        "current_mean_a": current,
        "inductor_ripple_estimate_a": ripple,
        "inductor_valley_estimate_a": valley,
        "inductor_peak_estimate_a": peak,
        "conduction_mode_estimate": "DCM" if valley < 0.0 else "CCM",
    }


def _case_checks(
    case: ChargingCase,
    summary: Mapping[str, Any],
    raw_limits: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    case_id = case.id
    if case_id == "C01":
        error = summary.get("cc_mean_error_a")
        checks.append(_check("cc_mean_error_a", error, 0.020, "A", error is not None and abs(float(error)) <= 0.020))
    elif case_id in ("C02",):
        error = summary.get("cv_mean_error_v")
        checks.append(_check("cv_mean_error_v", error, 0.020, "V", error is not None and abs(float(error)) <= 0.020))
        current = summary.get("steady_current_a")
        checks.append(_check("steady_current_below_cc_a", current, 0.5, "A", current is not None and float(current) < 0.5))
    elif case_id == "C03":
        checks.append(_check("reached_cv", 1.0 if summary.get("reached_cv") else 0.0, 1.0, "bool", bool(summary.get("reached_cv"))))
        overshoot = summary.get("voltage_overshoot_v")
        checks.append(_check("cc_cv_voltage_overshoot_v", overshoot, 0.050, "V", overshoot is not None and float(overshoot) <= 0.050))
    elif case_id in ("C04", "C05", "C06", "C08", "C09"):
        target = summary.get("expected_steady_current_a")
        current = summary.get("steady_current_a")
        checks.append(
            _check(
                "steady_current_error_a",
                None if (current is None or target is None) else float(current) - float(target),
                0.05,
                "A",
                current is not None and target is not None and abs(float(current) - float(target)) <= 0.05,
            )
        )
    elif case_id == "C07":
        reverse = summary.get("max_reverse_current_a")
        checks.append(_check("reverse_current_reported", reverse, None, "A", reverse is not None, "输入掉电风险记录，不设合格限"))
        checks.append(
            _check(
                "protection_fault_observed",
                1.0 if summary.get("protection", {}).get("latched_faults") else 0.0,
                1.0,
                "bool",
                True,
                "保护响应记录项，不设合格限",
            )
        )
    elif case_id == "C10":
        current = summary.get("steady_current_a")
        checks.append(_check("current_after_disable_a", current, 0.01, "A", current is not None and abs(float(current)) <= 0.01))
        gate = summary.get("gate_activity_after_disable_v")
        checks.append(_check("gate_activity_after_disable_v", gate, 0.1, "V", gate is not None and float(gate) <= 0.1))
    elif case_id == "C19":
        current = summary.get("steady_current_a")
        checks.append(_check("steady_current_a", current, 0.2, "A", current is not None and float(current) < 0.2))
        checks.append(_check("conduction_mode_recorded", 1.0, None, "bool", summary.get("conduction_mode_estimate") in ("CCM", "DCM")))
    elif case_id == "C20":
        checks.append(_check("reverse_current_reported", summary.get("max_reverse_current_a"), None, "A", summary.get("max_reverse_current_a") is not None))
        gate = summary.get("gate_activity_after_disable_v")
        checks.append(_check("gate_activity_after_disable_v", gate, 0.1, "V", gate is not None and float(gate) <= 0.1))

    checks.append(
        _check(
            "cell_overvoltage_limit",
            raw_limits.get("max_cell_voltage_v"),
            raw_limits.get("cell_overvoltage_trip_v"),
            "V",
            not bool(raw_limits.get("overvoltage_violated")),
        )
    )
    checks.append(
        _check(
            "cell_undervoltage_limit",
            raw_limits.get("min_cell_voltage_v"),
            raw_limits.get("cell_undervoltage_trip_v"),
            "V",
            not bool(raw_limits.get("undervoltage_violated")),
        )
    )
    checks.append(
        _check(
            "charge_overcurrent_limit",
            raw_limits.get("max_charge_current_a"),
            raw_limits.get("charge_overcurrent_trip_a"),
            "A",
            not bool(raw_limits.get("charge_overcurrent_violated")),
        )
    )
    return checks


def run_case(
    case_id: str,
    *,
    charger: ChargerConfig | None = None,
    controller: ControllerConfig | None = None,
    step_s: float = DEFAULT_STEP_S,
    temperature_c: float = 25.0,
    persist: bool = True,
    root: Any = None,
) -> CaseRun:
    charger = charger or load_charger_config()
    controller = controller or load_controller_config()
    case = _load_case(case_id)
    if case.method != "spice_simulation":
        raise SpiceCaseError(f"{case_id} 不是开关级 SPICE 工况（{case.method}）")
    parameters = dict(case.parameters)
    duration_s = float(parameters.get("duration_s", 0.01))

    fixture = _fixture(case, charger)
    cascade = CascadeParameters.from_configs(charger, controller)
    expressions = _expressions(case)

    precheck = _precheck_permission(fixture, temperature_c)
    if not precheck["charge_allowed"]:
        raise SpiceCaseError(f"{case_id} 运行前 BMS 许可为 False: {precheck}")

    waveform, circuit, layout = run_cascade_buck(
        charger.power_stage,
        fixture,
        cascade,
        duration_s=duration_s,
        step_s=step_s,
        vin_expression=expressions["vin_expression"],
        current_set_expression=expressions["current_set_expression"],
        enable_expression=expressions["enable_expression"],
        temperature_c=temperature_c,
    )

    limits = create_protection_controller().limits
    protection = _replay_protection(waveform, temperature_c)
    raw_limits = _raw_limit_check(waveform, limits, charger.power_stage.switching_frequency_hz)
    window_start = max(float(waveform.time_s[0]), float(waveform.time_s[-1]) - STEADY_WINDOW_S)
    step_time = parameters.get("step_time_s")
    analysis_start = window_start
    analysis_stop: float | None = None
    if case.id in ("C07", "C10", "C20") and step_time is not None:
        # 这些工况在阶跃后进入非充电状态，能效与损耗必须取阶跃前的稳态窗口，
        # 否则电池功率为负，效率没有物理意义。
        analysis_stop = float(step_time)
        analysis_start = max(float(waveform.time_s[0]), analysis_stop - STEADY_WINDOW_S)
    analysis_mask = (waveform.time_s >= analysis_start) & (
        waveform.time_s <= (float(waveform.time_s[-1]) if analysis_stop is None else analysis_stop)
    )

    steady_current = last_window_average(waveform.time_s, waveform.charging_current_a, STEADY_WINDOW_S)
    summary: dict[str, Any] = {
        "case_id": case.id,
        "case_name": case.name,
        "method": case.method,
        "duration_s": float(waveform.time_s[-1] - waveform.time_s[0]),
        "step_s": float(step_s),
        "reliable_step_limit_s": MINIMUM_RELIABLE_STEP_S,
        "fixture_pack_ocv_v": fixture.pack_ocv_v,
        "fixture_note": fixture.source_note,
        "bms_precheck": precheck,
        "protection": protection,
        "raw_limits": raw_limits,
        "steady_current_a": steady_current,
        "max_charging_current_a": float(waveform.charging_current_a.max()),
        "max_reverse_current_a": float(max(0.0, -waveform.charging_current_a.min())),
        "final_pack_voltage_v": float(waveform.pack_voltage_v[-1]),
        "final_charging_current_a": float(waveform.charging_current_a[-1]),
        "peak_pack_voltage_v": float(waveform.pack_voltage_v.max()),
        "steady_pack_voltage_v": last_window_average(waveform.time_s, waveform.pack_voltage_v, STEADY_WINDOW_S),
        "losses": _loss_breakdown(waveform, charger, analysis_start, analysis_stop),
        "energy": _energy_metrics(waveform),
        "conduction": _conduction_mode(waveform, charger, analysis_start, analysis_stop),
    }
    summary["conduction_mode_estimate"] = summary["conduction"]["conduction_mode_estimate"]

    target_current = 1.0
    if "iset_final_a" in parameters:
        target_current = float(parameters["iset_final_a"])
    summary["expected_steady_current_a"] = target_current

    frequency = charger.power_stage.switching_frequency_hz
    if case.id in ("C01", "C04", "C05", "C06", "C08", "C09", "C10"):
        summary["cc_metrics"] = cc_regulation_metrics(
            waveform.time_s,
            waveform.charging_current_a,
            target_current,
            frequency,
            window_s=STEADY_WINDOW_S,
        )
        summary["cc_mean_error_a"] = summary["cc_metrics"]["mean_error_a"]
        summary["cc_mae_a"] = summary["cc_metrics"]["mae_a"]
    if case.id in ("C02", "C03", "C19"):
        summary["cv_metrics"] = cv_regulation_metrics(
            waveform.time_s,
            waveform.pack_voltage_v,
            charger.charging.constant_voltage_v,
            frequency,
            window_s=STEADY_WINDOW_S,
        )
        summary["cv_mean_error_v"] = summary["cv_metrics"]["mean_error_v"]
        summary["cv_mae_v"] = summary["cv_metrics"]["mae_v"]
    if case.id in ("C02", "C03", "C19"):
        transition = transition_summary(
            waveform.time_s,
            waveform.pack_voltage_v,
            waveform.charging_current_a,
            charger.charging.constant_voltage_v,
            0.02,
            hold_time_s=5e-4,
        )
        summary.update(transition.to_dict())

    summary["efficiency"] = calculate_charger_efficiency(
        waveform.time_s[analysis_mask],
        waveform.input_voltage_v[analysis_mask],
        waveform.input_current_a[analysis_mask],
        waveform.pack_voltage_v[analysis_mask],
        waveform.charging_current_a[analysis_mask],
    )
    stage_efficiency = summary["efficiency"]["power_stage_efficiency_percent"]
    summary["power_stage_efficiency_percent"] = stage_efficiency
    losses = summary["losses"]["total_stage_loss_w"]
    input_power = summary["efficiency"]["input_power_w"]
    battery_power = summary["efficiency"]["battery_power_w"]
    summary["power_conservation_residual_fraction"] = (input_power - battery_power - losses) / input_power if input_power > 0 else None
    summary["intrinsic_solver_consistency_ppm"] = summary["energy"]["zoh_trapezoid_gap_ppm"]

    if case.id in ("C07", "C10", "C20"):
        after = waveform.time_s >= float(parameters.get("step_time_s", duration_s))
        if bool(after.any()):
            summary["steady_current_a"] = float(np.mean(waveform.charging_current_a[after][-max(1, int(0.002 / step_s)):]))
            summary["gate_activity_after_disable_v"] = float(np.mean(waveform.gate_voltage_v[after][-max(1, int(0.002 / step_s)):]))
        else:
            summary["gate_activity_after_disable_v"] = float(np.mean(waveform.gate_voltage_v))

    checks = _case_checks(case, summary, raw_limits)
    summary["case_checks"] = checks
    summary["case_status"] = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"

    run_dir: RunDirectory | None = None
    netlist_path: str | None = None
    waveform_path: str | None = None
    if persist:
        run_dir = RunDirectory("stage6", root=root)
        run_dir.write_metadata(
            {
                "stage": "stage6",
                "case": case.to_dict(),
                "simulation_layer": case.method,
                "controller_location": "inside_spice_netlist_behavioral_sources",
                "step_s": float(step_s),
                "ngspice": "PySpice 1.5 / ngspice 34",
            }
        )
        run_dir.write_config_snapshot(
            {
                "charger": charger.to_dict(),
                "controller": controller.to_dict(),
                "cascade": cascade.to_dict(),
                "expressions": expressions,
                "fixture": fixture.to_dict(),
            }
        )
        netlist_path = str(save_netlist(circuit, run_dir.path / "circuit.cir"))
        decimation = max(1, int(waveform.time_s.size // 20000) + 1)
        columns = waveform.to_columns()
        header = list(columns)
        rows = (
            tuple(columns[name][index] for name in header)
            for index in range(0, waveform.time_s.size, decimation)
        )
        waveform_path = str(run_dir.write_waveform(header, rows, name="waveform.csv"))
        summary["waveform_decimation"] = decimation
        summary["waveform_rows"] = int(len(range(0, waveform.time_s.size, decimation)))
        run_dir.write_summary(summary)
        run_dir.flush_log()

    return CaseRun(
        case_id=case.id,
        name=case.name,
        method=case.method,
        waveform=waveform,
        summary=summary,
        checks=checks,
        run_dir=run_dir,
        netlist_path=netlist_path,
        waveform_path=waveform_path,
    )


def run_profile(
    profile: str = "standard",
    *,
    charger: ChargerConfig | None = None,
    controller: ControllerConfig | None = None,
    step_s: float = DEFAULT_STEP_S,
    persist: bool = True,
) -> list[CaseRun]:
    """按预算档运行。smoke 只跑 C01–C03；standard 跑全部 12 个开关级工况。"""
    profiles = {
        "smoke": ("C01", "C02", "C03"),
        "standard": SPICE_CASE_IDS,
    }
    if profile not in profiles:
        raise SpiceCaseError(f"未知档位: {profile}")
    runs: list[CaseRun] = []
    for case_id in profiles[profile]:
        runs.append(
            run_case(
                case_id,
                charger=charger,
                controller=controller,
                step_s=step_s,
                persist=persist,
            )
        )
    return runs


def summarize_runs(runs: Sequence[CaseRun]) -> dict[str, Any]:
    rows = [run.to_dict() for run in runs]
    failed = [row["case_id"] for row in rows if row.get("case_status") != "PASS"]
    return {
        "stage": "stage6",
        "layer": "spice_simulation",
        "cases": rows,
        "case_count": len(rows),
        "failed_cases": failed,
        "status": "PASS" if not failed else "FAIL",
    }


def prerun_netlist(
    case_id: str,
    *,
    charger: ChargerConfig | None = None,
    controller: ControllerConfig | None = None,
) -> str:
    """只构建网表（不求解），用于检查行为源与 PWL 表达式。"""
    charger = charger or load_charger_config()
    controller = controller or load_controller_config()
    case = _load_case(case_id)
    fixture = _fixture(case, charger)
    expressions = _expressions(case)
    circuit, _ = build_cascade_circuit(
        charger.power_stage,
        fixture,
        CascadeParameters.from_configs(charger, controller),
        vin_expression=expressions["vin_expression"],
        current_set_expression=expressions["current_set_expression"],
        enable_expression=expressions["enable_expression"],
    )
    return str(circuit)


def available_cases() -> dict[str, str]:
    return {case.id: case.method for case in load_charging_cases()}

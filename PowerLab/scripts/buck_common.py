"""第三阶段 Buck 脚本共享流程：真实仿真 → 波形分析 → 验证 → 保存。

不生成任何伪造 SPICE 数据；如果求解或分析失败，异常直接上抛，
由脚本记录失败运行或退出非零。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from analysis.buck_theory import BuckTheoryResult, DcmTheoryResult, calculate_ideal_buck, calculate_ideal_dcm
from analysis.buck_validation import (
    BuckValidationLimits,
    BuckValidationReport,
    load_buck_validation_config,
    validate_buck_converter,
)
from analysis.buck_waveforms import PWMAnalysis, analyze_pwm_waveform, buck_waveforms_from_result
from analysis.conduction_mode import (
    ConductionMode,
    ConductionModeResult,
    classify_conduction_mode,
    theoretical_conduction_mode,
)
from analysis.steady_state import (
    SteadyStateWindow,
    capacitor_charge_balance,
    identify_steady_state,
    inductor_volt_second_balance,
    settling_time_s,
    slice_window,
    steady_state_metrics,
    time_weighted_mean,
)
from circuits.buck_config import BuckParameters
from simulations.artifacts import RESULTS_ROOT
from simulations.buck_runner import (
    DEFAULT_MAXIMUM_END_TIME_S,
    extended_end_time,
    run_buck_transient,
)
from simulations.models import SimulationResult
from storage.result_store import ResultStore

BUCK_RESULTS_ROOT = RESULTS_ROOT / "buck"
STAGE3_RESULTS_ROOT = RESULTS_ROOT / "buck_stage3"

#: 扩展仿真最多尝试次数。
MAX_EXTENSION_ATTEMPTS = 3


@dataclass(frozen=True)
class BuckCase:
    """一次完整 Buck 仿真分析结果。"""

    parameters: BuckParameters
    result: SimulationResult
    waveforms: pd.DataFrame
    pwm: PWMAnalysis
    window: SteadyStateWindow
    metrics: dict[str, Any] | None
    volt_second: dict[str, Any] | None
    charge_balance: dict[str, Any] | None
    mode: ConductionModeResult
    theory: BuckTheoryResult
    dcm_theory: DcmTheoryResult
    validation: BuckValidationReport | None
    extensions: tuple[dict[str, Any], ...]

    @property
    def simulated_end_s(self) -> float:
        return float(self.waveforms["time_s"].iloc[-1])

    @property
    def steady_cycle_boundaries_s(self) -> tuple[float, ...]:
        return tuple(
            boundary
            for boundary in self.pwm.cycle_boundaries_s
            if self.window.start_time_s - 1e-15
            <= boundary
            <= self.window.end_time_s + 1e-15
        )


def _not_settled_mode(
    time_s: np.ndarray,
    current: np.ndarray,
    note: str,
) -> ConductionModeResult:
    return ConductionModeResult(
        mode=ConductionMode.NOT_SETTLED,
        valley_current_a=float(current.min()),
        peak_current_a=float(current.max()),
        near_zero_threshold_a=float("nan"),
        near_zero_time_ratio=float("nan"),
        near_zero_duration_s=float("nan"),
        cycles_analyzed=0,
        reverse_current_anomaly=False,
        notes=note,
    )


def _analyze(
    parameters: BuckParameters,
    result: SimulationResult,
    *,
    validation_limits: BuckValidationLimits | None,
) -> BuckCase:
    waveforms = buck_waveforms_from_result(
        result.data, parameters.circuit.load_resistance_ohm
    )
    pwm = analyze_pwm_waveform(
        waveforms["time_s"],
        waveforms["gate_v"],
        low_voltage_v=parameters.pwm.low_voltage_v,
        high_voltage_v=parameters.pwm.high_voltage_v,
    )
    window = identify_steady_state(
        waveforms["time_s"],
        waveforms["vout_v"],
        waveforms["inductor_current_a"],
        pwm.cycle_boundaries_s,
        parameters.steady_state,
    )

    bounds = tuple(
        boundary
        for boundary in pwm.cycle_boundaries_s
        if window.start_time_s - 1e-15 <= boundary <= window.end_time_s + 1e-15
    )

    metrics: dict[str, Any] | None = None
    volt_second: dict[str, Any] | None = None
    charge_balance: dict[str, Any] | None = None
    if window.is_steady and len(bounds) >= 2:
        metrics = steady_state_metrics(
            waveforms["time_s"],
            {column: waveforms[column].to_numpy() for column in waveforms.columns},
            window,
            bounds,
        )
        volt_second = inductor_volt_second_balance(
            waveforms["time_s"],
            waveforms["inductor_voltage_v"],
            waveforms["inductor_current_a"],
            parameters.circuit.inductance_h,
            window,
        )
        charge_balance = capacitor_charge_balance(
            waveforms["time_s"],
            waveforms["capacitor_current_a"],
            waveforms["vout_v"],
            parameters.circuit.capacitance_f,
            window,
        )
        mode = classify_conduction_mode(
            waveforms["time_s"], waveforms["inductor_current_a"], bounds
        )
    else:
        mode = _not_settled_mode(
            waveforms["time_s"].to_numpy(),
            waveforms["inductor_current_a"].to_numpy(),
            f"steady state status is {window.status}; mode is not forced",
        )

    theory = calculate_ideal_buck(parameters.circuit)
    dcm_theory = calculate_ideal_dcm(parameters.circuit)

    validation: BuckValidationReport | None = None
    if validation_limits is not None:
        measured_voltage = None if metrics is None else metrics["output_voltage_mean_v"]
        measured_inductor_ripple = (
            None if metrics is None else metrics["inductor_current_ripple_app"]
        )
        measured_output_ripple = (
            None if metrics is None else metrics["output_voltage_ripple_vpp"]
        )
        theoretical_mode = theoretical_conduction_mode(
            theory.boundary_current_a, theory.ideal_output_current_a
        )
        validation = validate_buck_converter(
            expected_frequency_hz=parameters.circuit.switching_frequency_hz,
            measured_frequency_hz=pwm.mean_frequency_hz,
            expected_duty_cycle=parameters.pwm.duty_cycle,
            measured_duty_cycle=pwm.mean_duty_cycle,
            ideal_ccm_voltage_v=theory.ideal_output_voltage_v,
            measured_output_voltage_v=measured_voltage,
            ccm_assumption_valid=theory.ccm_assumption_valid,
            theoretical_inductor_ripple_app=theory.inductor_ripple_app,
            measured_inductor_ripple_app=measured_inductor_ripple,
            theoretical_capacitor_ripple_vpp=theory.capacitor_ripple_vpp,
            measured_output_ripple_vpp=measured_output_ripple,
            simulated_mode=mode.mode,
            theoretical_mode=theoretical_mode,
            steady_state_status=window.status,
            volt_second=volt_second,
            charge_balance=charge_balance,
            waveform_quality_ok=bool(result.metadata.get("quality", {}).get("valid", True)),
            limits=validation_limits,
        )

    return BuckCase(
        parameters=parameters,
        result=result,
        waveforms=waveforms,
        pwm=pwm,
        window=window,
        metrics=metrics,
        volt_second=volt_second,
        charge_balance=charge_balance,
        mode=mode,
        theory=theory,
        dcm_theory=dcm_theory,
        validation=validation,
        extensions=(),
    )


def run_and_analyze(
    parameters: BuckParameters,
    *,
    end_time_s: float | None = None,
    allow_extension: bool = True,
    maximum_end_time_s: float = DEFAULT_MAXIMUM_END_TIME_S,
    validation_limits: BuckValidationLimits | None = None,
) -> BuckCase:
    """真实仿真并按需延长结束时间，直到稳态或达到扩展上限。"""
    if not isinstance(parameters, BuckParameters):
        raise ValueError("parameters must be BuckParameters")

    requested_end = (
        parameters.transient.end_time_s if end_time_s is None else float(end_time_s)
    )
    result = run_buck_transient(parameters, end_time_s=requested_end)
    extensions: list[dict[str, Any]] = []

    case = _analyze(parameters, result, validation_limits=validation_limits)
    while allow_extension and not case.window.is_steady:
        next_end = extended_end_time(
            case.simulated_end_s, maximum_end_s=maximum_end_time_s
        )
        if next_end is None or len(extensions) >= MAX_EXTENSION_ATTEMPTS:
            break
        extended = run_buck_transient(parameters, end_time_s=next_end)
        extensions.append(
            {
                "from_end_s": case.simulated_end_s,
                "to_end_s": next_end,
                "previous_status": case.window.status,
                "previous_run_id": case.result.run_id,
                "new_run_id": extended.run_id,
            }
        )
        case = _analyze(parameters, extended, validation_limits=validation_limits)

    if extensions:
        extensions[-1]["final_status"] = case.window.status
        case = replace(case, extensions=tuple(extensions))
    return case


def startup_metrics(
    case: BuckCase,
    *,
    reference_voltage_v: float | None = None,
) -> dict[str, Any]:
    """启动过程指标（基于完整真实波形）。"""
    time = case.waveforms["time_s"].to_numpy()
    voltage = case.waveforms["vout_v"].to_numpy()
    current = case.waveforms["inductor_current_a"].to_numpy()
    reference = (
        float(case.window.mean_output_voltage_v)
        if reference_voltage_v is None and math.isfinite(case.window.mean_output_voltage_v)
        else float(reference_voltage_v or case.parameters.circuit.target_output_voltage_v)
    )

    settling = settling_time_s(time, voltage, reference)

    # 电感电流包含开关纹波，直接逐点判定会被纹波本身触发；
    # 先按完整开关周期求时间加权平均，再判断周期平均值是否稳定。
    cycle_times: list[float] = []
    cycle_means: list[float] = []
    boundaries = case.pwm.cycle_boundaries_s
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        window_time, window_current = slice_window(
            time, current, float(start), float(end)
        )
        cycle_times.append(0.5 * (float(start) + float(end)))
        cycle_means.append(time_weighted_mean(window_time, window_current))
    if len(cycle_means) >= 2:
        tail_count = max(1, len(cycle_means) // 5)
        reference_current = float(np.mean(cycle_means[-tail_count:]))
        current_settling = settling_time_s(
            np.asarray(cycle_times, dtype=float),
            np.asarray(cycle_means, dtype=float),
            reference_current,
            relative_band=0.05,
            absolute_band=0.02,
            minimum_hold_s=5e-4,
        )
    else:
        reference_current = float("nan")
        current_settling = None

    peak_voltage = float(voltage.max())
    peak_current = float(current.max())
    return {
        "reference_voltage_v": reference,
        "output_peak_v": peak_voltage,
        "output_overshoot_v": peak_voltage - reference,
        "output_overshoot_ratio": (peak_voltage - reference) / reference,
        "peak_inductor_current_a": peak_current,
        "peak_current_over_rated_ratio": peak_current
        / case.parameters.circuit.rated_output_current_a,
        "settling_time_vout_s": settling,
        "settling_time_il_s": current_settling,
        "cycle_mean_current_reference_a": reference_current,
        "settling_band_relative": 0.02,
        "settling_band_absolute_v": 0.01,
        "current_settling_band_relative": 0.05,
        "data_source": "spice_simulation",
    }


def _window_frame(waveforms: pd.DataFrame, start_s: float, end_s: float) -> pd.DataFrame:
    time = waveforms["time_s"].to_numpy()
    _, output = slice_window(time, waveforms["vout_v"].to_numpy(), start_s, end_s)
    mask = (time > start_s) & (time < end_s)
    columns: dict[str, Any] = {
        "time_s": np.concatenate(([start_s], time[mask], [end_s]))
    }
    for column in waveforms.columns:
        if column == "time_s":
            continue
        values = waveforms[column].to_numpy()
        columns[column] = np.concatenate(
            (
                [np.interp(start_s, time, values)],
                values[mask],
                [np.interp(end_s, time, values)],
            )
        )
    frame = pd.DataFrame(columns)
    if len(frame) != len(output):
        raise ValueError("steady-state window frame length mismatch")
    return frame


def _theory_payload(case: BuckCase) -> dict[str, Any]:
    return {
        "data_source": "analytical_theory",
        "ideal_ccm": case.theory.to_dict(),
        "ideal_dcm": case.dcm_theory.to_dict(),
        "equations": {
            "duty": "Vout = D * Vin",
            "inductor_ripple": "dIL = (Vin - Vout) * D / (L * f)",
            "capacitor_ripple": "dVout = dIL / (8 * f * C)",
            "boundary_current": "I_boundary = dIL / 2",
            "dcm_ratio": "M = 2 / (1 + sqrt(1 + 4K/D^2)), K = 2L/(R*T)",
        },
        "note": "ideal CCM unless stated otherwise; excludes switch RON, diode drop, ESR and control dynamics",
    }


def _spice_payload(case: BuckCase) -> dict[str, Any]:
    return {
        "data_source": "spice_simulation",
        "run_id": case.result.run_id,
        "simulated_end_s": case.simulated_end_s,
        "point_count": case.result.point_count,
        "duration_ms": case.result.duration_ms,
        "pwm": case.pwm.to_dict(),
        "steady_state": case.window.to_dict(),
        "steady_state_metrics": case.metrics,
        "conduction_mode": case.mode.to_dict(),
        "time_step_statistics": case.result.metadata.get("time_step_statistics", {}),
        "waveform_quality": case.result.metadata.get("quality", {}),
        "analysis_command": case.result.metadata.get("analysis_command"),
        "extensions": list(case.extensions),
    }


def _comparison_payload(case: BuckCase) -> dict[str, Any]:
    metrics = case.metrics or {}
    return {
        "data_source": "comparison",
        "frequency_hz": {
            "theory": case.parameters.circuit.switching_frequency_hz,
            "simulated": case.pwm.mean_frequency_hz,
            "relative_error": (
                case.pwm.mean_frequency_hz - case.parameters.circuit.switching_frequency_hz
            )
            / case.parameters.circuit.switching_frequency_hz,
        },
        "duty_cycle": {
            "configured": case.parameters.pwm.duty_cycle,
            "measured": case.pwm.mean_duty_cycle,
            "absolute_error": case.pwm.mean_duty_cycle - case.parameters.pwm.duty_cycle,
        },
        "output_voltage_v": {
            "ideal_ccm": case.theory.ideal_output_voltage_v,
            "simulated": metrics.get("output_voltage_mean_v"),
        },
        "inductor_ripple_app": {
            "ideal_ccm": case.theory.inductor_ripple_app,
            "simulated": metrics.get("inductor_current_ripple_app"),
        },
        "output_ripple_vpp": {
            "ideal_ccm": case.theory.capacitor_ripple_vpp,
            "simulated": metrics.get("output_voltage_ripple_vpp"),
        },
        "conduction_mode": {
            "theoretical": theoretical_conduction_mode(
                case.theory.boundary_current_a, case.theory.ideal_output_current_a
            ).value,
            "simulated": case.mode.mode.value,
        },
        "validation_status": None if case.validation is None else case.validation.status,
    }


def _theory_table(case: BuckCase) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scope, payload in (
        ("ideal_ccm", case.theory.to_dict()),
        ("ideal_dcm", case.dcm_theory.to_dict()),
    ):
        rows.extend(
            {"scope": scope, "quantity": key, "value": value}
            for key, value in payload.items()
        )
    return pd.DataFrame(rows)


def _comparison_table(case: BuckCase) -> pd.DataFrame:
    if case.validation is None:
        return pd.DataFrame([_comparison_payload(case)])
    rows = [
        {
            "name": check.name,
            "category": check.category,
            "status": check.status,
            "measured": check.measured,
            "reference": check.reference,
            "error": check.error,
            "tolerance": check.tolerance,
            "unit": check.unit,
            "note": check.note,
        }
        for check in case.validation.checks
    ]
    return pd.DataFrame(rows)


def save_case(
    case: BuckCase,
    store: ResultStore,
    run_dir: Path,
    *,
    figures: Mapping[str, str | Path] | None = None,
    extra_json_files: Mapping[str, Any] | None = None,
    extra_table_files: Mapping[str, pd.DataFrame] | None = None,
    summary_extra: Mapping[str, Any] | None = None,
    log_lines: tuple[str, ...] = (),
) -> Path:
    """保存完整运行数据、理论与验证结果。"""
    if not isinstance(case, BuckCase):
        raise ValueError("case must be BuckCase")
    if not isinstance(store, ResultStore):
        raise ValueError("store must be ResultStore")
    run_directory = Path(run_dir)
    if not run_directory.is_dir():
        raise FileNotFoundError(f"运行目录不存在: {run_directory}")

    json_files: dict[str, Any] = {
        "theoretical_results.json": _theory_payload(case),
        "spice_results.json": _spice_payload(case),
        "comparison.json": _comparison_payload(case),
        "steady_state.json": {
            "data_source": "spice_simulation",
            "window": case.window.to_dict(),
            "metrics": case.metrics,
            "volt_second_balance": case.volt_second,
            "charge_balance": case.charge_balance,
            "cycle_boundaries_s": list(case.steady_cycle_boundaries_s),
        },
        "conduction_mode.json": case.mode.to_dict(),
        "extensions.json": {
            "attempts": list(case.extensions),
            "final_end_s": case.simulated_end_s,
            "final_status": case.window.status,
        },
    }
    if case.validation is not None:
        json_files["validation.json"] = case.validation.to_dict()
    if extra_json_files:
        json_files.update(extra_json_files)

    table_files: dict[str, pd.DataFrame] = {}
    if case.metrics is not None:
        table_files["steady_state_waveform.csv"] = _window_frame(
            case.waveforms, case.window.start_time_s, case.window.end_time_s
        )
    if extra_table_files:
        table_files.update(extra_table_files)

    summary: dict[str, Any] = {
        "case": "asynchronous_buck_open_loop",
        "mode": case.mode.mode.value,
        "steady_state_status": case.window.status,
        "simulated_end_s": case.simulated_end_s,
        "extension_attempts": len(case.extensions),
        "validation_status": None if case.validation is None else case.validation.status,
        "specification_type": "project_assumption",
        "model_type": case.parameters.model_type,
        "data_source": "spice_simulation",
        "theory_source": "analytical_theory",
    }
    if case.metrics is not None:
        summary.update(
            {
                "output_voltage_mean_v": case.metrics["output_voltage_mean_v"],
                "output_voltage_ripple_vpp": case.metrics["output_voltage_ripple_vpp"],
                "inductor_current_ripple_app": case.metrics["inductor_current_ripple_app"],
            }
        )
    if summary_extra:
        summary.update(summary_extra)

    lines = [
        f"buck case: mode={case.mode.mode.value}, steady={case.window.status}",
        f"simulated_end_s={case.simulated_end_s:.9g}",
        f"validation={None if case.validation is None else case.validation.status}",
        f"extensions={len(case.extensions)}",
        *log_lines,
    ]

    return store.save_result(
        case.result,
        run_dir=run_directory,
        waveform=case.waveforms,
        config_snapshot=case.parameters.to_dict(),
        analysis_parameters={
            "buck_parameters": case.parameters.to_dict(),
            "waveform_columns": list(case.waveforms.columns),
            "steady_state_bounds_s": list(case.steady_cycle_boundaries_s),
        },
        theory=_theory_table(case),
        comparison=_comparison_table(case),
        summary=summary,
        figures=figures,
        extra_json=json_files,
        extra_tables=table_files,
        log_lines=lines,
    )


def default_validation_limits() -> BuckValidationLimits:
    return load_buck_validation_config()


def record_failure(
    analysis_name: str,
    error: BaseException,
    *,
    parameters: BuckParameters | None = None,
    root: Path = BUCK_RESULTS_ROOT,
    log_lines: tuple[str, ...] = (),
) -> Path:
    """记录失败运行；不会生成波形或伪造结果文件。"""
    store = ResultStore(root=Path(root))
    return store.save_failure(
        analysis_name=analysis_name,
        error=error,
        parameters=None if parameters is None else parameters.to_dict(),
        config_snapshot=None if parameters is None else parameters.to_dict(),
        log_lines=log_lines,
    )

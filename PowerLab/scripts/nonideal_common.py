"""第四阶段脚本共享流水线：真实仿真 → 波形 → 稳态 → 功率 → 能量 → 应力。

只被 ``scripts/*.py`` 调用，不参与库层导入。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.buck_waveforms import (
    NONIDEAL_WAVEFORM_COLUMNS,
    analyze_pwm_waveform,
    extract_nonideal_waveforms,
)
from analysis.device_stress import DeviceStress, compute_device_stress
from analysis.energy_balance import EnergyBalance, energy_balance
from analysis.loss_analysis import (
    SwitchingEnergy,
    conduction_loss_in_on_windows,
    switching_energy,
)
from analysis.model_comparison import ModelSummary, summarize_model
from analysis.power_metrics import (
    PowerAccounting,
    compute_power_accounting,
    frame_window,
    relative_residual,
)
from analysis.steady_state import SteadyStateWindow, identify_steady_state
from circuits.nonideal_buck import VariantFeatures, get_variant_features
from circuits.nonideal_config import NonidealBuckConfig, load_validation_limits
from simulations.artifacts import RESULTS_ROOT
from simulations.buck_runner import extended_end_time
from simulations.models import SimulationResult
from simulations.nonideal_buck_runner import run_nonideal_buck_transient
from simulations.exceptions import SimulationExecutionError
from storage.result_store import ResultStore

#: 第四阶段结果目录。
NONIDEAL_RESULTS_ROOT = RESULTS_ROOT / "nonideal_buck"
DEVICE_RESULTS_ROOT = RESULTS_ROOT / "devices"
STAGE4_RESULTS_ROOT = RESULTS_ROOT / "buck_stage4"

#: 默认允许的最长扩展仿真时间。
DEFAULT_MAXIMUM_END_TIME_S = 10e-3

#: 数值收敛重试的最大内部步长候选（秒）。ngspice 在个别采样点上
#: 会因 "timestep too small" 中止，换一个最大步长通常可继续；
#: 每次重试都记录在结果 metadata 中，不隐藏失败。
CONVERGENCE_STEP_CANDIDATES = (None, 20e-9, 12.5e-9, 10e-9, 6.25e-9)


@dataclass
class NonidealCase:
    """一次非理想 Buck 运行的完整分析结果。"""

    config: NonidealBuckConfig
    variant: str
    features: VariantFeatures
    result: SimulationResult
    frame: pd.DataFrame
    pwm: Any
    steady: SteadyStateWindow
    window_frame: pd.DataFrame
    accounting: PowerAccounting
    energy: EnergyBalance
    stress: DeviceStress
    stress_full_run: DeviceStress
    switching: SwitchingEnergy
    conduction_estimate_w: float | None
    summary: ModelSummary
    rds_on_ohm: float | None = None
    checks: dict[str, Any] = field(default_factory=dict)
    extension_attempts: int = 0

    @property
    def run_id(self) -> str:
        return self.result.run_id

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "label": self.features.label,
            "model_features": self.features.to_dict(),
            "steady_state": self.steady.to_dict(),
            "steady_state_achieved": self.steady.is_steady,
            "extension_attempts": self.extension_attempts,
            "power": self.accounting.to_dict(),
            "energy_balance": self.energy.to_dict(),
            "stress": self.stress.to_dict(),
            "stress_full_run": self.stress_full_run.to_dict(),
            "switching": self.switching.to_dict(),
            "conduction_estimate_w": self.conduction_estimate_w,
            "model_summary": self.summary.to_dict(),
            "checks": self.checks,
            "time_step_statistics": self.result.metadata.get("time_step_statistics", {}),
            "data_source": "spice_simulation",
        }


def gate_levels(config: NonidealBuckConfig, features: VariantFeatures) -> tuple[float, float]:
    """返回用于边沿检测的栅极低/高电平。"""
    if features.uses_floating_driver:
        return config.gate_driver.low_voltage_v, config.gate_driver.drive_voltage_v
    return 0.0, 5.0


def build_frame(
    result: SimulationResult,
    config: NonidealBuckConfig,
    features: VariantFeatures,
) -> pd.DataFrame:
    """从结果中提取统一波形帧。"""
    return extract_nonideal_waveforms(
        result.data,
        load_resistance_ohm=config.load_resistance_ohm,
        gate_resistance_ohm=(
            config.gate_driver.gate_resistance_ohm if features.uses_floating_driver else None
        ),
        pulldown_resistance_ohm=(
            config.gate_driver.gate_source_pulldown_ohm
            if features.uses_floating_driver
            else None
        ),
    )


def effective_dcr(config: NonidealBuckConfig, features: VariantFeatures) -> float:
    return config.inductor.dcr_ohm if features.uses_dcr else 0.0


def effective_esr(config: NonidealBuckConfig, features: VariantFeatures) -> float:
    return config.capacitor.esr_ohm if features.uses_esr else 0.0


def analyze_result(
    result: SimulationResult,
    config: NonidealBuckConfig,
    variant: str,
    *,
    rds_on_ohm: float | None = None,
    validation: dict[str, Any] | None = None,
    extension_attempts: int = 0,
) -> NonidealCase:
    """对已完成的真实仿真结果做完整分析。"""
    if not isinstance(result, SimulationResult):
        raise ValueError("result must be SimulationResult")
    features = get_variant_features(variant)
    frame = build_frame(result, config, features)
    low, high = gate_levels(config, features)
    pwm = analyze_pwm_waveform(
        frame["time_s"],
        frame["mosfet_vgs_v"],
        low_voltage_v=low,
        high_voltage_v=high,
    )
    if pwm.complete_cycles < 1:
        raise ValueError("no complete switching cycle was recorded")

    steady = identify_steady_state(
        frame["time_s"],
        frame["vout_v"],
        frame["inductor_current_a"],
        pwm.cycle_start_times_s,
        config.steady_state,
    )

    if steady.is_steady:
        window = frame_window(frame, steady.start_time_s, steady.end_time_s)
    else:
        # 未稳态时使用最后 ``minimum_cycles`` 个完整周期做参考窗口，并保留标记
        boundaries = np.asarray(pwm.cycle_start_times_s, dtype=float)
        count = min(config.steady_state.minimum_cycles, max(len(boundaries) - 1, 1))
        start = float(boundaries[-count - 1])
        end = float(boundaries[-1])
        window = frame_window(frame, start, end)

    accounting = compute_power_accounting(
        window,
        dcr_ohm=effective_dcr(config, features),
        esr_ohm=effective_esr(config, features),
        gate_resistance_ohm=(
            config.gate_driver.gate_resistance_ohm if features.uses_floating_driver else 0.0
        ),
        pulldown_resistance_ohm=(
            config.gate_driver.gate_source_pulldown_ohm
            if features.uses_floating_driver
            else 0.0
        ),
    )
    energy = energy_balance(accounting)
    stress = compute_device_stress(window)
    stress_full = compute_device_stress(frame)

    transitions = switching_energy(
        window["time_s"],
        window["mosfet_vds_v"],
        window["mosfet_drain_terminal_current_a"],
        window["mosfet_vgs_v"],
        low_level_v=low,
        high_level_v=high,
    )

    conduction_estimate: float | None = None
    if rds_on_ohm is not None:
        conduction_estimate = conduction_loss_in_on_windows(
            window["time_s"],
            window["mosfet_drain_terminal_current_a"],
            window["mosfet_vgs_v"],
            rds_on_ohm=float(rds_on_ohm),
            gate_threshold_v=0.5 * (low + high),
        )

    summary = summarize_model(
        variant=features.variant,
        label=features.label,
        frame=window,
        accounting=accounting,
        stress=stress,
        steady_state_achieved=steady.is_steady,
        steady_state_start_s=steady.start_time_s,
        steady_state_end_s=steady.end_time_s,
        sample_count=len(result.data),
    )

    limits = validation if validation is not None else load_validation_limits()
    checks = evaluate_checks(summary, accounting, energy, limits)

    return NonidealCase(
        config=config,
        variant=features.variant,
        features=features,
        result=result,
        frame=frame,
        pwm=pwm,
        steady=steady,
        window_frame=window,
        accounting=accounting,
        energy=energy,
        stress=stress,
        stress_full_run=stress_full,
        switching=transitions,
        conduction_estimate_w=conduction_estimate,
        summary=summary,
        rds_on_ohm=None if rds_on_ohm is None else float(rds_on_ohm),
        checks=checks,
        extension_attempts=extension_attempts,
    )


def evaluate_checks(
    summary: ModelSummary,
    accounting: PowerAccounting,
    energy: EnergyBalance,
    limits: dict[str, Any],
) -> dict[str, Any]:
    """按验收判据给出检查项（不修改数据）。"""
    integration = limits["integration"]
    power_limits = limits["power"]
    output_ok = (
        integration["output_voltage_min_v"]
        <= summary.output_voltage_mean_v
        <= integration["output_voltage_max_v"]
    )
    residual = relative_residual(accounting)
    residual_limit = power_limits["energy_balance_relative_residual_warning"]
    residual_ok = bool(np.isfinite(residual) and abs(residual) <= residual_limit)

    efficiency_ok = True
    efficiency_note = "ok"
    if accounting.efficiency_power_stage_percent is None:
        efficiency_ok = False
        efficiency_note = "efficiency_undefined"
    elif accounting.efficiency_power_stage_percent > power_limits["efficiency_warning_above_percent"]:
        efficiency_ok = False
        efficiency_note = "efficiency_above_limit_check_boundaries"

    steady_ok = summary.steady_state_achieved or not integration["require_steady_state"]

    checks = {
        "output_voltage_in_range": {
            "value": summary.output_voltage_mean_v,
            "range": [integration["output_voltage_min_v"], integration["output_voltage_max_v"]],
            "passed": bool(output_ok),
        },
        "steady_state": {
            "value": summary.steady_state_achieved,
            "passed": bool(steady_ok),
        },
        "power_balance_residual": {
            "value": residual,
            "limit": residual_limit,
            "passed": residual_ok,
        },
        "efficiency": {
            "value": accounting.efficiency_power_stage_percent,
            "passed": bool(efficiency_ok),
            "note": efficiency_note,
        },
        "energy_balance_status": {
            "value": energy.status,
            "passed": energy.status != "excessive",
        },
    }
    return {
        "passed": all(item["passed"] for item in checks.values()),
        "checks": checks,
        "limits_source": "configs/nonideal_validation.yaml",
    }


def run_case(
    config: NonidealBuckConfig,
    variant: str,
    *,
    end_time_s: float | None = None,
    maximum_end_time_s: float = DEFAULT_MAXIMUM_END_TIME_S,
    allow_extension: bool = True,
    rds_on_ohm: float | None = None,
    validation: dict[str, Any] | None = None,
    temperature_c: float | None = None,
    max_step_time_s: float | None = None,
) -> NonidealCase:
    """真实运行并在未稳态时自动延长仿真时间。"""
    result = run_nonideal_buck_transient(
        config,
        variant,
        end_time_s=end_time_s,
        max_step_time_s=max_step_time_s,
        temperature_c=temperature_c,
    )
    case = analyze_result(
        result,
        config,
        variant,
        rds_on_ohm=rds_on_ohm,
        validation=validation,
    )
    attempts = 0
    while (
        not case.steady.is_steady
        and allow_extension
        and attempts < 3
    ):
        current_end = float(result.data["time_s"].iloc[-1])
        next_end = extended_end_time(current_end, maximum_end_s=maximum_end_time_s)
        if next_end is None:
            break
        attempts += 1
        result = run_nonideal_buck_transient(
            config,
            variant,
            end_time_s=next_end,
            max_step_time_s=max_step_time_s,
            temperature_c=temperature_c,
        )
        case = analyze_result(
            result,
            config,
            variant,
            rds_on_ohm=rds_on_ohm,
            validation=validation,
            extension_attempts=attempts,
        )
    return case


def run_case_with_retries(
    config: NonidealBuckConfig,
    variant: str,
    *,
    max_step_time_s: float | None = None,
    candidates: tuple[float | None, ...] = CONVERGENCE_STEP_CANDIDATES,
    **kwargs: Any,
) -> NonidealCase:
    """在 ``timestep too small`` 时换用更小的最大步长重试。

    每个失败尝试都记录在 ``result.metadata['convergence_retries']`` 中；
    只有真实求解成功的运行才会返回。全部候选失败时抛出最后一次异常。
    """
    attempts: list[float | None] = (
        [max_step_time_s] if max_step_time_s is not None else list(candidates)
    )
    failures: list[dict[str, Any]] = []
    last_error: SimulationExecutionError | None = None
    for step in attempts:
        try:
            case = run_case(
                config, variant, max_step_time_s=step, **kwargs
            )
        except SimulationExecutionError as error:
            last_error = error
            failures.append({
                "max_step_time_s": step,
                "error": f"{type(error).__name__}: {error}",
            })
            continue
        used = config.transient.max_step_time_s if step is None else step
        case.result.metadata["used_max_step_time_s"] = used
        case.result.metadata["convergence_retries"] = failures
        return case
    if last_error is None:  # pragma: no cover - defensive
        raise RuntimeError("no simulation attempt was made")
    raise last_error


def save_case(
    case: NonidealCase,
    store: ResultStore,
    run_dir: Path,
    *,
    figures: dict[str, Path] | None = None,
    extra_tables: dict[str, pd.DataFrame] | None = None,
    extra_json: dict[str, Any] | None = None,
) -> Path:
    """保存波形、功率、能量、应力与配置快照。"""
    snapshot = copy.deepcopy(case.config.to_dict())
    snapshot["circuit"]["model_variant"] = case.variant
    snapshot["circuit"]["model_features"] = case.features.to_dict()

    tables = {
        "waveform_steady.csv": case.window_frame,
    }
    if extra_tables:
        tables.update(extra_tables)

    payload = {
        "power": case.accounting.to_dict(),
        "energy_balance": case.energy.to_dict(),
        "stress_steady": case.stress.to_dict(),
        "stress_full_run": case.stress_full_run.to_dict(),
        "switching": case.switching.to_dict(),
        "conduction_estimate_w": case.conduction_estimate_w,
        "steady_state": case.steady.to_dict(),
        "model_features": case.features.to_dict(),
        "pwm": {
            "complete_cycles": case.pwm.complete_cycles,
            "mean_frequency_hz": case.pwm.mean_frequency_hz,
            "mean_duty_cycle": case.pwm.mean_duty_cycle,
        },
        "checks": case.checks,
    }
    if extra_json:
        payload.update(extra_json)

    return store.save_result(
        case.result,
        run_dir=run_dir,
        config_snapshot=snapshot,
        waveform=case.frame,
        summary=case.to_summary_dict(),
        figures=figures or {},
        extra_tables=tables,
        extra_json=payload,
        analysis_parameters={
            "variant": case.variant,
            "rds_on_ohm": case.rds_on_ohm,
            "window_start_s": case.window_frame["time_s"].iloc[0],
            "window_end_s": case.window_frame["time_s"].iloc[-1],
            "data_source": "spice_simulation",
        },
        log_lines=[
            f"variant={case.variant}",
            f"steady_state={case.steady.status}",
            f"efficiency_power_stage_percent={case.accounting.efficiency_power_stage_percent}",
            f"residual_ratio={case.energy.residual_ratio}",
        ],
    )


def assert_waveform_columns(frame: pd.DataFrame) -> None:
    """校验统一波形列完整（供测试与脚本使用）。"""
    missing = [name for name in NONIDEAL_WAVEFORM_COLUMNS if name not in frame.columns]
    if missing:
        raise ValueError(f"nonideal waveform missing columns: {missing}")

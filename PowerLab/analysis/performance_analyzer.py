"""性能分析器：把一次真实 SPICE 瞬态结果转换为统一性能指标。

流程固定为：

真实波形 → 稳态识别 → 稳态窗口 → 时域/纹波/功率/开关/频谱/谐波 → 质量检查 → 限值判定

分析器只读取 ``SimulationResult``，不触发仿真，也不修改原始波形。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from circuits.nonideal_buck import get_variant_features
from circuits.nonideal_config import NonidealBuckConfig
from simulations.models import SimulationResult

from .buck_waveforms import analyze_pwm_waveform, extract_nonideal_waveforms
from .harmonic_analysis import analyze_harmonics, total_harmonic_distortion
from .performance_judge import judge_profile, summarize_checks
from .performance_models import (
    DataSource,
    EfficiencyMetrics,
    MetricStatus,
    PerformanceMetric,
    PerformanceResult,
    PowerMetrics,
    QualityMetrics,
    RegulationMetrics,
    RippleMetrics,
    SpectrumMetrics,
    SwitchingMetrics,
    VoltageMetrics,
    CurrentMetrics,
    load_analysis_config,
    load_limits,
    resolve_profile,
)
from .performance_quality import (
    QualityIssue,
    check_metric_consistency,
    check_power_residual,
    check_spectrum,
    check_steady_state,
    check_switching,
    check_waveform_frame,
    quality_summary,
)
from .power_metrics import compute_power_accounting
from .ripple_analysis import (
    analyze_ripple,
    cycle_ripple_statistics,
    decompose_output_ripple,
    theoretical_ripple_components,
)
from .spectrum_analysis import analyze_spectrum
from .steady_state import identify_steady_state, settling_time_s
from .switching_analysis import analyze_switching
from .time_domain import (
    clip_time_window,
    maximum_value,
    minimum_value,
    peak_to_peak,
    time_weighted_mean,
    time_weighted_rms,
)

REQUIRED_COLUMNS = NONIDEAL_REQUIRED = (
    "time_s",
    "vout_v",
    "switch_node_v",
    "input_current_a",
    "inductor_current_a",
    "capacitor_current_a",
    "load_current_a",
    "mosfet_vds_v",
    "mosfet_vgs_v",
    "drive_vgs_command_v",
)


def _metric(
    name: str,
    value: float | int | str | None,
    unit: str,
    *,
    status: MetricStatus = MetricStatus.AVAILABLE,
    source: DataSource = DataSource.SPICE_DERIVED,
    method: str = "time_weighted_integration",
    message: str = "",
    conditions: dict[str, Any] | None = None,
) -> PerformanceMetric:
    return PerformanceMetric(
        name=name,
        value=value,
        unit=unit,
        status=status,
        data_source=source,
        method=method,
        message=message,
        conditions={} if conditions is None else conditions,
    )


def _clip_frame(frame: pd.DataFrame, start_s: float, end_s: float) -> pd.DataFrame:
    """对所有列在窗口边界做线性插值，返回连续窗口。"""
    time = frame["time_s"].to_numpy(dtype=float)
    mask = (time > float(start_s)) & (time < float(end_s))
    window_time = np.concatenate(
        ([float(start_s)], time[mask], [float(end_s)])
    )
    data: dict[str, np.ndarray] = {"time_s": window_time}
    for column in frame.columns:
        if column == "time_s":
            continue
        values = frame[column].to_numpy(dtype=float)
        data[column] = np.concatenate(
            (
                [np.interp(float(start_s), time, values)],
                values[mask],
                [np.interp(float(end_s), time, values)],
            )
        )
    return pd.DataFrame(data)


@dataclass
class PerformanceAnalyzer:
    """第五阶段统一分析入口。"""

    analysis_config: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None
    profile: str = "baseline_open_loop"

    def __post_init__(self) -> None:
        if self.analysis_config is None:
            self.analysis_config = load_analysis_config()
        if self.limits is None:
            self.limits = load_limits()
        self._analysis = self.analysis_config["analysis"]

    def analyze(
        self,
        result: SimulationResult,
        config: NonidealBuckConfig,
        *,
        variant: str | None = None,
        include_spectrum: bool = True,
        profile: str | None = None,
    ) -> PerformanceResult:
        if not isinstance(result, SimulationResult):
            raise ValueError("result must be a SimulationResult")
        if not isinstance(config, NonidealBuckConfig):
            raise ValueError("config must be a NonidealBuckConfig")
        selected_variant = variant or str(
            result.metadata.get("model_variant", {}).get("variant", "E")
        )
        features = get_variant_features(selected_variant)
        frame = extract_nonideal_waveforms(
            result.data,
            load_resistance_ohm=config.load_resistance_ohm,
            gate_resistance_ohm=(
                config.gate_driver.gate_resistance_ohm
                if features.uses_floating_driver
                else None
            ),
            pulldown_resistance_ohm=(
                config.gate_driver.gate_source_pulldown_ohm
                if features.uses_floating_driver
                else None
            ),
        )

        issues: list[QualityIssue] = []
        issues.extend(check_waveform_frame(frame, REQUIRED_COLUMNS))

        time = frame["time_s"].to_numpy(dtype=float)
        vout = frame["vout_v"].to_numpy(dtype=float)
        inductor_current = frame["inductor_current_a"].to_numpy(dtype=float)
        command = frame["drive_vgs_command_v"].to_numpy(dtype=float)
        command_low = float(np.percentile(command, 1.0))
        command_high = float(np.percentile(command, 99.0))
        if command_high <= command_low:
            raise ValueError("drive command has no measurable swing")
        pwm = analyze_pwm_waveform(
            time,
            command,
            low_voltage_v=command_low,
            high_voltage_v=command_high,
        )
        if pwm.complete_cycles < 1:
            raise ValueError("no complete switching cycle was recorded")

        steady = identify_steady_state(
            time,
            vout,
            inductor_current,
            pwm.cycle_start_times_s,
            config.steady_state,
        )
        achieved = steady.status == "STEADY_STATE"
        steady_payload = {
            "start_time_s": steady.start_time_s,
            "end_time_s": steady.end_time_s,
            "complete_cycles": steady.complete_cycles,
            "voltage_mean_change_ratio": steady.voltage_mean_change_ratio,
            "current_mean_change_ratio": steady.current_mean_change_ratio,
            "ripple_change_ratio": steady.ripple_change_ratio,
            "status": steady.status,
            "achieved": achieved,
            "mean_output_voltage_v": steady.mean_output_voltage_v,
            "mean_inductor_current_a": steady.mean_inductor_current_a,
        }
        issues.extend(check_steady_state(steady_payload))
        status = MetricStatus.AVAILABLE if achieved else MetricStatus.NOT_SETTLED
        message = "" if achieved else "steady state not reached"

        window = _clip_frame(frame, steady.start_time_s, steady.end_time_s)
        window_time = window["time_s"].to_numpy(dtype=float)

        # ---------- 电压 / 纹波 ----------
        ripple = analyze_ripple(window_time, window["vout_v"].to_numpy(dtype=float))
        target = float(config.target_output_voltage_v)
        error = ripple.mean_value - target
        voltage_metrics = {
            "output_voltage_target_v": _metric(
                "output_voltage_target_v",
                target,
                "V",
                source=DataSource.PROJECT_ASSUMPTION,
                method="configured design target",
            ),
            "output_voltage_mean_v": _metric(
                "output_voltage_mean_v", ripple.mean_value, "V", status=status, message=message
            ),
            "output_voltage_max_v": _metric(
                "output_voltage_max_v", ripple.maximum_value, "V", status=status, message=message
            ),
            "output_voltage_min_v": _metric(
                "output_voltage_min_v", ripple.minimum_value, "V", status=status, message=message
            ),
            "output_voltage_ripple_vpp": _metric(
                "output_voltage_ripple_vpp",
                ripple.peak_to_peak,
                "V",
                status=status,
                method="max-min of raw samples in window",
                message=message,
            ),
            "output_voltage_ac_rms_v": _metric(
                "output_voltage_ac_rms_v", ripple.ac_rms, "V", status=status, message=message
            ),
            "output_voltage_total_rms_v": _metric(
                "output_voltage_total_rms_v", ripple.total_rms, "V", status=status, message=message
            ),
            "output_voltage_error_v": _metric(
                "output_voltage_error_v",
                error,
                "V",
                status=status,
                method="mean output minus configured target",
                message=message,
            ),
            "output_voltage_abs_error_v": _metric(
                "output_voltage_abs_error_v", abs(error), "V", status=status, message=message
            ),
            "output_voltage_error_percent": _metric(
                "output_voltage_error_percent",
                abs(error) / target * 100.0,
                "%",
                status=status,
                message=message,
            ),
        }

        # ---------- 电流 ----------
        il = window["inductor_current_a"].to_numpy(dtype=float)
        ic = window["capacitor_current_a"].to_numpy(dtype=float)
        iin = window["input_current_a"].to_numpy(dtype=float)
        il_mean = time_weighted_mean(window_time, il)
        il_rms = time_weighted_rms(window_time, il)
        il_ripple = peak_to_peak(il)
        current_metrics = {
            "inductor_current_mean_a": _metric(
                "inductor_current_mean_a", il_mean, "A", status=status, message=message
            ),
            "inductor_current_peak_a": _metric(
                "inductor_current_peak_a", maximum_value(il), "A", status=status, message=message
            ),
            "inductor_current_valley_a": _metric(
                "inductor_current_valley_a", minimum_value(il), "A", status=status, message=message
            ),
            "inductor_current_rms_a": _metric(
                "inductor_current_rms_a", il_rms, "A", status=status, message=message
            ),
            "inductor_current_ripple_a": _metric(
                "inductor_current_ripple_a",
                il_ripple,
                "A",
                status=status,
                method="max-min of raw samples in window",
                message=message,
            ),
            "inductor_current_ripple_ratio_percent": _metric(
                "inductor_current_ripple_ratio_percent",
                (il_ripple / abs(il_mean) * 100.0) if abs(il_mean) > 1e-12 else None,
                "%",
                status=status if abs(il_mean) > 1e-12 else MetricStatus.INVALID_DATA,
                message=message if abs(il_mean) > 1e-12 else "mean inductor current near zero",
            ),
            "capacitor_current_mean_a": _metric(
                "capacitor_current_mean_a",
                time_weighted_mean(window_time, ic),
                "A",
                status=status,
                message=message,
            ),
            "capacitor_current_rms_a": _metric(
                "capacitor_current_rms_a", time_weighted_rms(window_time, ic), "A", status=status, message=message
            ),
            "capacitor_current_positive_peak_a": _metric(
                "capacitor_current_positive_peak_a", maximum_value(ic), "A", status=status, message=message
            ),
            "capacitor_current_negative_peak_a": _metric(
                "capacitor_current_negative_peak_a", minimum_value(ic), "A", status=status, message=message
            ),
            "capacitor_current_ripple_a": _metric(
                "capacitor_current_ripple_a", peak_to_peak(ic), "A", status=status, message=message
            ),
            "input_current_mean_a": _metric(
                "input_current_mean_a",
                time_weighted_mean(window_time, iin),
                "A",
                status=status,
                message=message,
            ),
            "input_current_rms_a": _metric(
                "input_current_rms_a", time_weighted_rms(window_time, iin), "A", status=status, message=message
            ),
            "input_current_positive_peak_a": _metric(
                "input_current_positive_peak_a", maximum_value(iin), "A", status=status, message=message
            ),
            "input_current_negative_peak_a": _metric(
                "input_current_negative_peak_a", minimum_value(iin), "A", status=status, message=message
            ),
        }

        # ---------- 功率 / 效率 ----------
        dcr = config.inductor.dcr_ohm if features.uses_dcr else 0.0
        esr = config.capacitor.esr_ohm if features.uses_esr else 0.0
        accounting = compute_power_accounting(
            window,
            dcr_ohm=dcr,
            esr_ohm=esr,
            gate_resistance_ohm=(
                config.gate_driver.gate_resistance_ohm
                if features.uses_floating_driver
                else 0.0
            ),
            pulldown_resistance_ohm=(
                config.gate_driver.gate_source_pulldown_ohm
                if features.uses_floating_driver
                else 0.0
            ),
        )
        total_input = accounting.input_average_power_w + accounting.driver_average_power_w
        residual_ratio = (
            accounting.residual_w / total_input if total_input > 0 else None
        )
        power_metrics = {
            "input_power_w": _metric(
                "input_power_w", accounting.input_average_power_w, "W", status=status, message=message
            ),
            "driver_power_w": _metric(
                "driver_power_w", accounting.driver_average_power_w, "W", status=status, message=message
            ),
            "total_input_power_w": _metric(
                "total_input_power_w", total_input, "W", status=status, message=message
            ),
            "output_power_w": _metric(
                "output_power_w", accounting.output_average_power_w, "W", status=status, message=message
            ),
            "mosfet_loss_w": _metric(
                "mosfet_loss_w", accounting.mosfet_network_average_power_w, "W", status=status, message=message
            ),
            "diode_loss_w": _metric(
                "diode_loss_w", accounting.diode_average_power_w, "W", status=status, message=message
            ),
            "dcr_loss_w": _metric(
                "dcr_loss_w", accounting.dcr_loss_w, "W", status=status, message=message
            ),
            "esr_loss_w": _metric(
                "esr_loss_w", accounting.esr_loss_w, "W", status=status, message=message
            ),
            "gate_resistor_loss_w": _metric(
                "gate_resistor_loss_w", accounting.gate_resistor_loss_w, "W", status=status, message=message
            ),
            "pulldown_loss_w": _metric(
                "pulldown_loss_w", accounting.pulldown_loss_w, "W", status=status, message=message
            ),
            "total_loss_w": _metric(
                "total_loss_w", accounting.total_loss_w, "W", status=status, message=message
            ),
            "residual_w": _metric(
                "residual_w", accounting.residual_w, "W", status=status, message=message
            ),
            "power_residual_ratio": _metric(
                "power_residual_ratio",
                residual_ratio,
                "1",
                status=status if residual_ratio is not None else MetricStatus.INVALID_DATA,
                method="residual / (input + driver)",
                message=message,
            ),
        }
        efficiency_metrics = {
            "efficiency_power_stage_percent": _metric(
                "efficiency_power_stage_percent",
                accounting.efficiency_power_stage_percent,
                "%",
                status=status,
                message=message,
            ),
            "efficiency_system_percent": _metric(
                "efficiency_system_percent",
                accounting.efficiency_system_percent,
                "%",
                status=status,
                method="output / (input + driver)",
                message=message,
            ),
        }

        # ---------- 纹波细节 ----------
        ripple_details: dict[str, Any] = {}
        ripple_metrics: dict[str, PerformanceMetric] = {}
        try:
            decomposition = decompose_output_ripple(window)
            ripple_details = decomposition.to_dict()
            ripple_metrics.update(
                {
                    "output_voltage_esr_ripple_vpp": _metric(
                        "output_voltage_esr_ripple_vpp",
                        decomposition.esr_vpp_v,
                        "V",
                        status=status,
                        message=message,
                    ),
                    "output_voltage_capacitor_ripple_vpp": _metric(
                        "output_voltage_capacitor_ripple_vpp",
                        decomposition.capacitor_internal_vpp_v,
                        "V",
                        status=status,
                        message=message,
                    ),
                }
            )
        except ValueError as error:
            issues.append(
                QualityIssue("E_MISSING_WAVEFORM", "ERROR", f"ripple decomposition failed: {error}")
            )
        boundaries = [
            float(item)
            for item in pwm.cycle_boundaries_s
            if steady.start_time_s <= item <= steady.end_time_s
        ]
        cycle_stats = (
            cycle_ripple_statistics(
                window_time,
                window["vout_v"].to_numpy(dtype=float),
                boundaries,
            )
            if len(boundaries) >= 2
            else {}
        )
        if cycle_stats:
            ripple_metrics.update(
                {
                    "cycle_ripple_mean_v": _metric(
                        "cycle_ripple_mean_v", cycle_stats["cycle_ripple_mean"], "V", status=status, message=message
                    ),
                    "cycle_ripple_max_v": _metric(
                        "cycle_ripple_max_v", cycle_stats["cycle_ripple_max"], "V", status=status, message=message
                    ),
                    "cycle_ripple_std_v": _metric(
                        "cycle_ripple_std_v", cycle_stats["cycle_ripple_std"], "V", status=status, message=message
                    ),
                }
            )
            if cycle_stats["drift_warning"]:
                issues.append(
                    QualityIssue(
                        "W_RIPPLE_DRIFT",
                        "WARNING",
                        "window peak-to-peak is much larger than per-cycle ripple; slow drift may be present",
                        "output_voltage_ripple_vpp",
                    )
                )
        theoretical = theoretical_ripple_components(
            il_ripple, pwm.mean_frequency_hz, config.capacitor.capacitance_f, esr
        )
        ripple_details["theoretical"] = theoretical

        # ---------- 开关 ----------
        switching_metrics: dict[str, PerformanceMetric] = {
            "switching_frequency_hz": _metric(
                "switching_frequency_hz",
                pwm.mean_frequency_hz,
                "Hz",
                status=status,
                method="complete-cycle boundary statistics of real gate command",
                message=message,
            ),
            "pwm_duty_cycle": _metric(
                "pwm_duty_cycle",
                pwm.mean_duty_cycle,
                "1",
                status=status,
                method="mean of complete-cycle pulse widths",
                message=message,
            ),
            "pwm_duty_absolute_error": _metric(
                "pwm_duty_absolute_error",
                abs(pwm.mean_duty_cycle - config.duty_cycle),
                "1",
                status=status,
                method="|measured duty - configured duty|",
                message=message,
            ),
        }
        switching_details: dict[str, Any] = {}
        if features.uses_mosfet:
            switching = analyze_switching(
                window,
                low_ratio=float(self._analysis["switching"]["low_threshold_ratio"]),
                high_ratio=float(self._analysis["switching"]["high_threshold_ratio"]),
                minimum_edge_samples=int(self._analysis["switching"]["minimum_edge_samples"]),
                switching_frequency_hz=pwm.mean_frequency_hz,
            )
            switching_details = switching.to_dict()
            issues.extend(check_switching(switching))
            for name, edge in (
                ("switching_turn_on_time_s", switching.turn_on),
                ("switching_turn_off_time_s", switching.turn_off),
            ):
                switching_metrics[name] = _metric(
                    name,
                    edge.duration_s,
                    "s",
                    status=(
                        status
                        if edge.status == "AVAILABLE"
                        else MetricStatus.NOT_RESOLVED
                    ),
                    method="10%-90% VDS crossing with linear interpolation",
                    message=edge.note,
                )
            switching_metrics["switching_turn_on_delay_s"] = _metric(
                "switching_turn_on_delay_s",
                switching.turn_on_delay_s,
                "s",
                status=status if switching.turn_on_delay_s is not None else MetricStatus.NOT_RESOLVED,
                message="" if switching.turn_on_delay_s is not None else "delay not resolved",
            )
            switching_metrics["switching_turn_off_delay_s"] = _metric(
                "switching_turn_off_delay_s",
                switching.turn_off_delay_s,
                "s",
                status=status if switching.turn_off_delay_s is not None else MetricStatus.NOT_RESOLVED,
                message="" if switching.turn_off_delay_s is not None else "delay not resolved",
            )
            switching_metrics["switching_turn_on_energy_j"] = _metric(
                "switching_turn_on_energy_j", switching.turn_on_energy_j, "J", status=status, message=message
            )
            switching_metrics["switching_turn_off_energy_j"] = _metric(
                "switching_turn_off_energy_j", switching.turn_off_energy_j, "J", status=status, message=message
            )
            switching_metrics["switching_total_energy_j"] = _metric(
                "switching_total_energy_j", switching.cycle_energy_j, "J", status=status, message=message
            )
            switching_metrics["switching_power_w"] = _metric(
                "switching_power_w", switching.switching_power_w, "W", status=status, message=message
            )
            resolved = (
                switching.turn_on.status == "AVAILABLE"
                and switching.turn_off.status == "AVAILABLE"
            )
            switching_metrics["switching_edge_resolution_ok"] = _metric(
                "switching_edge_resolution_ok",
                1.0 if resolved else 0.0,
                "1",
                status=MetricStatus.AVAILABLE,
                method="both edges have at least the configured minimum raw samples",
            )
        else:
            for name in (
                "switching_turn_on_time_s",
                "switching_turn_off_time_s",
                "switching_turn_on_delay_s",
                "switching_turn_off_delay_s",
                "switching_turn_on_energy_j",
                "switching_turn_off_energy_j",
                "switching_total_energy_j",
                "switching_power_w",
                "switching_edge_resolution_ok",
            ):
                switching_metrics[name] = _metric(
                    name,
                    None,
                    "s" if name.endswith("_s") else ("J" if name.endswith("_j") else ("W" if name.endswith("_w") else "1")),
                    status=MetricStatus.NOT_APPLICABLE,
                    message="SW baseline has no MOSFET gate or channel",
                )

        # ---------- 频谱 / 谐波 ----------
        spectrum_metrics: dict[str, PerformanceMetric] = {}
        spectrum_metadata: dict[str, Any] = {}
        harmonic_entries: list[dict[str, Any]] = []
        spectrum = None
        spectrum_start = float(steady.start_time_s)
        spectrum_end = float(time[-1])
        try:
            settled = settling_time_s(
                time,
                vout,
                float(steady.mean_output_voltage_v),
                relative_band=0.005,
                absolute_band=0.002,
                minimum_hold_s=5e-4,
            )
            if settled is not None and spectrum_end - settled > spectrum_end - spectrum_start:
                spectrum_start = float(settled)
        except (ValueError, IndexError):
            settled = None

        spectrum_config = self._analysis["spectrum"]
        if include_spectrum and bool(spectrum_config["enabled"]):
            duration = spectrum_end - spectrum_start
            if duration * pwm.mean_frequency_hz < 10:
                spectrum_metrics["spectrum_frequency_resolution_hz"] = _metric(
                    "spectrum_frequency_resolution_hz",
                    None,
                    "Hz",
                    status=MetricStatus.NOT_RESOLVED,
                    message="fewer than 10 complete cycles available for spectrum",
                )
                issues.append(
                    QualityIssue(
                        "W_SPECTRUM_UNDER_RESOLVED",
                        "WARNING",
                        "spectrum skipped: fewer than 10 complete cycles",
                    )
                )
            else:
                spectrum = analyze_spectrum(
                    time,
                    vout,
                    start_s=spectrum_start,
                    end_s=spectrum_end,
                    switching_frequency_hz=pwm.mean_frequency_hz,
                    samples_per_cycle=int(spectrum_config["samples_per_cycle"]),
                    window_name=str(spectrum_config["window"]),
                    maximum_samples=int(spectrum_config["maximum_samples"]),
                )
                issues.extend(
                    check_spectrum(
                        spectrum,
                        preferred_cycles=int(spectrum_config["preferred_cycles"]),
                    )
                )
                spectrum_metadata = {
                    **spectrum.metadata(),
                    "window_start_s": spectrum.resample.window_start_s,
                    "window_end_s": spectrum.resample.window_end_s,
                }
                spectrum_metrics = {
                    "spectrum_fundamental_frequency_hz": _metric(
                        "spectrum_fundamental_frequency_hz",
                        pwm.mean_frequency_hz,
                        "Hz",
                        status=status,
                        method="measured switching frequency used as harmonic base",
                        message=message,
                    ),
                    "spectrum_frequency_resolution_hz": _metric(
                        "spectrum_frequency_resolution_hz",
                        spectrum.resample.frequency_resolution_hz,
                        "Hz",
                    ),
                    "spectrum_nyquist_hz": _metric(
                        "spectrum_nyquist_hz", spectrum.resample.nyquist_hz, "Hz"
                    ),
                    "spectrum_trusted_max_hz": _metric(
                        "spectrum_trusted_max_hz", spectrum.resample.trusted_max_hz, "Hz"
                    ),
                    "spectrum_window_cycles": _metric(
                        "spectrum_window_cycles", float(spectrum.resample.complete_cycles), "1"
                    ),
                }
                harmonics = analyze_harmonics(
                    spectrum,
                    pwm.mean_frequency_hz,
                    maximum_order=int(spectrum_config["maximum_harmonic_order"]),
                    tolerance_ratio=float(spectrum_config["harmonic_tolerance_ratio"]),
                    minimum_snr=float(spectrum_config["minimum_harmonic_snr"]),
                )
                harmonic_entries = [entry.to_dict() for entry in harmonics]
                thd = total_harmonic_distortion(harmonics)
                spectrum_metrics["thd_percent"] = _metric(
                    "thd_percent",
                    thd["thd_percent"],
                    "%",
                    status=(
                        MetricStatus.AVAILABLE
                        if thd["status"] == "AVAILABLE"
                        else MetricStatus.NOT_RESOLVED
                    ),
                    method="sum of resolved harmonic RMS over fundamental RMS",
                    message=thd["note"],
                )

        quality_metrics = {
            "energy_balance_residual_ratio": _metric(
                "energy_balance_residual_ratio",
                residual_ratio,
                "1",
                status=status if residual_ratio is not None else MetricStatus.INVALID_DATA,
                method="residual power / (input + driver); same window as energy balance",
                message=message,
            ),
            "waveform_sample_count": _metric(
                "waveform_sample_count",
                float(window_time.size),
                "1",
                status=MetricStatus.AVAILABLE,
                method="samples in steady window",
            ),
        }

        groups = {
            "voltage": VoltageMetrics(voltage_metrics),
            "current": CurrentMetrics(current_metrics),
            "ripple": RippleMetrics(ripple_metrics),
            "power": PowerMetrics(power_metrics),
            "efficiency": EfficiencyMetrics(efficiency_metrics),
            "switching": SwitchingMetrics(switching_metrics),
            "spectrum": SpectrumMetrics(spectrum_metrics),
            "regulation": RegulationMetrics({}),
            "quality": QualityMetrics(quality_metrics),
        }
        flat: dict[str, PerformanceMetric] = {}
        for group in groups.values():
            flat.update(group.flatten())

        issues.extend(check_metric_consistency(flat))
        issues.extend(
            check_power_residual(
                residual_ratio,
                maximum_ratio=float(
                    self._analysis["quality"]["maximum_power_residual_ratio"]
                ),
            )
        )

        profile_name = profile or self.profile
        profile_rules = resolve_profile(self.limits, profile_name)
        checks = judge_profile(flat, profile_rules, profile_name=profile_name)
        summary = summarize_checks(checks)

        quality = quality_summary(issues)
        overall = summary["overall_status"]
        if not quality["passed"] and overall == "PASS":
            overall = "ERROR"

        notes = [
            "voltage/current/ripple metrics come from real SPICE samples in the steady window",
            "efficiency_power_stage excludes driver power; efficiency_system includes it",
            "residual power is reported separately and never assigned to a device",
        ]
        if not achieved:
            notes.append("steady state was not reached; steady metrics are diagnostic only")
        if spectrum_metadata:
            notes.append(
                "spectrum uses linear resampling of the real waveform; "
                "trusted band is limited by the largest raw sample gap"
            )

        return PerformanceResult(
            run_id=result.run_id,
            circuit_name=result.circuit_name,
            variant=selected_variant,
            data_source=result.data_source,
            steady_state=steady_payload,
            groups=groups,
            checks=tuple(checks),
            quality=quality,
            overall_status=overall,
            notes=tuple(notes),
            spectrum_metadata=spectrum_metadata,
            cycle_statistics=cycle_stats,
            ripple_decomposition=ripple_details,
            harmonic_entries=tuple(harmonic_entries),
            switching_details=switching_details,
            frame=frame,
            window_frame=window,
            spectrum=spectrum,
            circuit_netlist=getattr(result, "circuit_netlist", None),
            raw_point_count=int(len(frame)),
        )

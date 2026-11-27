"""数据质量检查。

错误码统一为 ``E_*``（阻止结论）与 ``W_*``（需要人工注意）。
质量问题不会被静默忽略，也不会被包装成 PASS。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .performance_models import MetricStatus, PerformanceMetric
from .spectrum_analysis import SpectrumResult
from .switching_analysis import SwitchingAnalysis

ERROR_CODES = (
    "E_MISSING_WAVEFORM",
    "E_NONFINITE_DATA",
    "E_TIME_AXIS_INVALID",
    "E_METRIC_INCONSISTENT",
    "E_UNIT_MISMATCH",
    "E_POWER_RESIDUAL_EXCESSIVE",
    "E_NEGATIVE_RIPPLE",
    "E_EMPTY_SPECTRUM",
)


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    message: str
    metric: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "metric": self.metric,
        }


def check_waveform_frame(
    frame: pd.DataFrame,
    required_columns: Iterable[str],
) -> list[QualityIssue]:
    """检查波形列、有限性与时间轴。"""
    issues: list[QualityIssue] = []
    if not isinstance(frame, pd.DataFrame):
        return [
            QualityIssue("E_MISSING_WAVEFORM", "ERROR", "frame is not a DataFrame")
        ]
    missing = [name for name in required_columns if name not in frame.columns]
    if missing:
        issues.append(
            QualityIssue(
                "E_MISSING_WAVEFORM",
                "ERROR",
                f"missing waveform columns: {missing}",
            )
        )
    if "time_s" in frame.columns:
        time = frame["time_s"].to_numpy(dtype=float)
        if time.size < 2:
            issues.append(
                QualityIssue("E_TIME_AXIS_INVALID", "ERROR", "time axis has fewer than 2 samples")
            )
        else:
            if not np.isfinite(time).all():
                issues.append(
                    QualityIssue("E_TIME_AXIS_INVALID", "ERROR", "time axis contains non-finite values")
                )
            elif np.any(np.diff(time) <= 0):
                issues.append(
                    QualityIssue("E_TIME_AXIS_INVALID", "ERROR", "time axis is not strictly increasing")
                )
    numeric = frame.select_dtypes(include=[np.number])
    if not numeric.empty and not np.isfinite(numeric.to_numpy(dtype=float)).all():
        issues.append(
            QualityIssue("E_NONFINITE_DATA", "ERROR", "waveform contains NaN or infinity")
        )
    return issues


def check_metric_consistency(metrics: Mapping[str, PerformanceMetric]) -> list[QualityIssue]:
    """检查同一物理量内部的一致性。"""
    issues: list[QualityIssue] = []

    def numeric(name: str) -> float | None:
        metric = metrics.get(name)
        return None if metric is None else metric.numeric()

    vmax = numeric("output_voltage_max_v")
    vmin = numeric("output_voltage_min_v")
    vpp = numeric("output_voltage_ripple_vpp")
    mean = numeric("output_voltage_mean_v")
    if None not in (vmax, vmin) and float(vmax) < float(vmin):
        issues.append(
            QualityIssue(
                "E_METRIC_INCONSISTENT",
                "ERROR",
                f"output_voltage_max_v ({vmax}) < output_voltage_min_v ({vmin})",
                "output_voltage_max_v",
            )
        )
    if vpp is not None and float(vpp) < 0:
        issues.append(
            QualityIssue(
                "E_NEGATIVE_RIPPLE",
                "ERROR",
                f"ripple is negative: {vpp}",
                "output_voltage_ripple_vpp",
            )
        )
    if None not in (vmax, vmin, vpp, mean):
        if abs((float(vmax) - float(vmin)) - float(vpp)) > 1e-9 + 1e-6 * abs(float(vpp)):
            issues.append(
                QualityIssue(
                    "E_METRIC_INCONSISTENT",
                    "ERROR",
                    "ripple does not match max-min of the same window",
                    "output_voltage_ripple_vpp",
                )
            )
        if not (float(vmin) <= float(mean) <= float(vmax)):
            issues.append(
                QualityIssue(
                    "E_METRIC_INCONSISTENT",
                    "ERROR",
                    "mean voltage lies outside [min, max]",
                    "output_voltage_mean_v",
                )
            )

    efficiency = numeric("efficiency_power_stage_percent")
    if efficiency is not None and not 0.0 <= float(efficiency) <= 100.5:
        issues.append(
            QualityIssue(
                "E_METRIC_INCONSISTENT",
                "ERROR",
                f"power-stage efficiency out of physical range: {efficiency}",
                "efficiency_power_stage_percent",
            )
        )

    for name, metric in metrics.items():
        if metric.status == MetricStatus.AVAILABLE and metric.value is None:
            issues.append(
                QualityIssue(
                    "E_METRIC_INCONSISTENT",
                    "ERROR",
                    f"metric {name} is AVAILABLE but has no value",
                    name,
                )
            )
        if metric.unit == "" and metric.status == MetricStatus.AVAILABLE:
            issues.append(
                QualityIssue(
                    "E_UNIT_MISMATCH",
                    "WARNING",
                    f"metric {name} has no unit",
                    name,
                )
            )
    return issues


def check_power_residual(
    residual_ratio: float | None,
    *,
    maximum_ratio: float = 0.05,
) -> list[QualityIssue]:
    """功率残差比例超限时给出错误。"""
    if residual_ratio is None:
        return []
    if abs(float(residual_ratio)) > float(maximum_ratio):
        return [
            QualityIssue(
                "E_POWER_RESIDUAL_EXCESSIVE",
                "ERROR",
                f"power residual ratio {residual_ratio:.6g} exceeds {maximum_ratio:.6g}",
                "power_residual_ratio",
            )
        ]
    return []


def check_spectrum(
    spectrum: SpectrumResult | None,
    *,
    preferred_cycles: int,
) -> list[QualityIssue]:
    """检查频谱样本量与周期数，不足时只告警。"""
    if spectrum is None:
        return []
    issues: list[QualityIssue] = []
    if spectrum.frequency_hz.size == 0:
        issues.append(QualityIssue("E_EMPTY_SPECTRUM", "ERROR", "spectrum is empty"))
        return issues
    if not np.isfinite(spectrum.amplitude_peak).all():
        issues.append(
            QualityIssue("E_NONFINITE_DATA", "ERROR", "spectrum contains non-finite amplitude")
        )
    if spectrum.resample.complete_cycles < int(preferred_cycles):
        issues.append(
            QualityIssue(
                "W_SPECTRUM_UNDER_RESOLVED",
                "WARNING",
                (
                    f"only {spectrum.resample.complete_cycles} complete cycles in spectrum window "
                    f"(preferred {preferred_cycles}); frequency resolution "
                    f"{spectrum.resample.frequency_resolution_hz:.1f} Hz"
                ),
                "spectrum_frequency_resolution_hz",
            )
        )
    return issues


def check_switching(switching: SwitchingAnalysis | None) -> list[QualityIssue]:
    """边沿未解析时告警，不阻断其余指标。"""
    if switching is None:
        return []
    issues: list[QualityIssue] = []
    for edge in (switching.turn_on, switching.turn_off):
        if edge.status != "AVAILABLE":
            issues.append(
                QualityIssue(
                    "W_EDGE_NOT_RESOLVED",
                    "WARNING",
                    f"{edge.name} not resolved: {edge.note}",
                    "switching_edge_resolution_ok",
                )
            )
    return issues


def check_steady_state(steady_state: Mapping[str, Any]) -> list[QualityIssue]:
    """未进入稳态时给出错误（默认要求稳态）。"""
    if not bool(steady_state.get("achieved", False)):
        return [
            QualityIssue(
                "E_NOT_SETTLED",
                "ERROR",
                "steady state was not reached; steady-state metrics are not valid",
            )
        ]
    return []


def quality_summary(issues: Iterable[QualityIssue]) -> dict[str, Any]:
    """汇总质量问题。"""
    items = list(issues)
    errors = [item for item in items if item.severity == "ERROR"]
    warnings = [item for item in items if item.severity == "WARNING"]
    return {
        "passed": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "error_codes": sorted({item.code for item in errors}),
        "warning_codes": sorted({item.code for item in warnings}),
        "issues": [item.to_dict() for item in items],
    }

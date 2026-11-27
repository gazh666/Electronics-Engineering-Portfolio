"""输出电压 / 电流纹波分析。

区分四个容易混淆的量：

- 平均直流分量 ``mean``；
- 总有效值 ``total_rms``（含直流，5 V 输出接近 5 V）；
- 去直流交流纹波有效值 ``ac_rms``；
- 峰峰值 ``peak_to_peak``（直接来自原始样本，不做平滑）。

同时提供逐周期峰峰值统计与 ESR 纹波分解。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .time_domain import (
    clip_time_window,
    maximum_value,
    minimum_value,
    peak_to_peak,
    time_weighted_ac_rms,
    time_weighted_mean,
    time_weighted_rms,
    validate_time_series,
)

#: 平均值接近 0 时不再计算相对纹波百分比。
RIPPLE_PERCENT_EPSILON = 1e-12


@dataclass(frozen=True)
class RippleResult:
    """单通道波形的纹波分析结果。"""

    mean_value: float
    minimum_value: float
    maximum_value: float
    peak_to_peak: float
    total_rms: float
    ac_rms: float
    ripple_percent: float | None
    sample_count: int
    start_time_s: float
    end_time_s: float
    unit: str = "V"
    data_source: str = "spice_derived"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean_value": self.mean_value,
            "minimum_value": self.minimum_value,
            "maximum_value": self.maximum_value,
            "peak_to_peak": self.peak_to_peak,
            "total_rms": self.total_rms,
            "ac_rms": self.ac_rms,
            "ripple_percent": self.ripple_percent,
            "sample_count": self.sample_count,
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "unit": self.unit,
            "data_source": self.data_source,
            "method": "time_weighted_integration_of_raw_samples",
        }


def analyze_ripple(time_s: Any, values: Any, *, unit: str = "V") -> RippleResult:
    """对真实波形计算平均、峰峰值、总 RMS 与交流 RMS。"""
    time, array = validate_time_series(time_s, values)
    mean_value = time_weighted_mean(time, array)
    minimum = minimum_value(array)
    maximum = maximum_value(array)
    ripple_pp = peak_to_peak(array)
    total_rms = time_weighted_rms(time, array)
    ac_rms = time_weighted_ac_rms(time, array)
    ripple_percent = (
        ripple_pp / abs(mean_value) * 100.0
        if abs(mean_value) > RIPPLE_PERCENT_EPSILON
        else None
    )
    return RippleResult(
        mean_value=float(mean_value),
        minimum_value=float(minimum),
        maximum_value=float(maximum),
        peak_to_peak=float(ripple_pp),
        total_rms=float(total_rms),
        ac_rms=float(ac_rms),
        ripple_percent=None if ripple_percent is None else float(ripple_percent),
        sample_count=int(time.size),
        start_time_s=float(time[0]),
        end_time_s=float(time[-1]),
        unit=unit,
    )


def cycle_ripple_values(
    time_s: Any,
    values: Any,
    cycle_boundaries_s: Iterable[float],
) -> list[float]:
    """逐完整周期峰峰值序列（边界处线性插值）。"""
    time, array = validate_time_series(time_s, values)
    boundaries = np.asarray(list(cycle_boundaries_s), dtype=float)
    if boundaries.ndim != 1 or boundaries.size < 2:
        raise ValueError("at least two cycle boundaries are required")
    if not np.isfinite(boundaries).all() or not np.all(np.diff(boundaries) > 0):
        raise ValueError("cycle boundaries must be finite and strictly increasing")
    ripples: list[float] = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        _, window = clip_time_window(time, array, float(start), float(end))
        ripples.append(peak_to_peak(window))
    return ripples


def cycle_ripple_statistics(
    time_s: Any,
    values: Any,
    cycle_boundaries_s: Iterable[float],
) -> dict[str, Any]:
    """逐周期纹波、周期平均纹波与周期最大纹波。

    若整窗口峰峰值明显大于单周期纹波均值，说明存在周期间漂移，
    ``drift_warning`` 会被置为 ``True``，供数据质量模块引用。
    """
    per_cycle = cycle_ripple_values(time_s, values, cycle_boundaries_s)
    if not per_cycle:
        raise ValueError("no complete cycle was available")
    whole = analyze_ripple(time_s, values)
    mean_cycle = float(np.mean(per_cycle))
    values_array = np.asarray(per_cycle, dtype=float)
    drift_warning = bool(
        mean_cycle > 0 and whole.peak_to_peak > 2.0 * mean_cycle
    )
    return {
        "per_cycle_ripple": [float(item) for item in per_cycle],
        "cycle_count": int(values_array.size),
        "cycle_ripple_mean": mean_cycle,
        "cycle_ripple_max": float(np.max(values_array)),
        "cycle_ripple_min": float(np.min(values_array)),
        "cycle_ripple_std": float(np.std(values_array)),
        "window_ripple": float(whole.peak_to_peak),
        "drift_warning": drift_warning,
        "data_source": "spice_derived",
    }


@dataclass(frozen=True)
class RippleDecomposition:
    """``Vout = Vcap_internal + V_ESR`` 的波形级一致性检查。"""

    output_vpp_v: float
    capacitor_internal_vpp_v: float
    esr_vpp_v: float
    reconstruction_mae_v: float
    reconstruction_rmse_v: float
    reconstruction_max_abs_v: float
    sample_count: int
    start_time_s: float
    end_time_s: float
    data_source: str = "spice_derived"

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_vpp_v": self.output_vpp_v,
            "capacitor_internal_vpp_v": self.capacitor_internal_vpp_v,
            "esr_vpp_v": self.esr_vpp_v,
            "reconstruction_mae_v": self.reconstruction_mae_v,
            "reconstruction_rmse_v": self.reconstruction_rmse_v,
            "reconstruction_max_abs_v": self.reconstruction_max_abs_v,
            "sample_count": self.sample_count,
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "method": "residual = Vout - Vcap_internal - V_ESR from real node voltages",
            "note": (
                "this is a circuit-relationship consistency check, not an independent "
                "instrument measurement; do not add the two theoretical Vpp values "
                "and call it the exact output ripple"
            ),
            "data_source": self.data_source,
        }


def decompose_output_ripple(frame: pd.DataFrame) -> RippleDecomposition:
    """用真实波形验证 ``Vout - Vcap - V_ESR ≈ 0``。"""
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("frame must be a pandas.DataFrame")
    required = (
        "time_s",
        "vout_v",
        "capacitor_internal_voltage_v",
        "capacitor_esr_voltage_v",
    )
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"ripple decomposition requires columns: {missing}")

    time = frame["time_s"].to_numpy(dtype=float)
    vout = frame["vout_v"].to_numpy(dtype=float)
    cap = frame["capacitor_internal_voltage_v"].to_numpy(dtype=float)
    esr = frame["capacitor_esr_voltage_v"].to_numpy(dtype=float)
    validate_time_series(time, vout, "vout_v")
    residual = vout - cap - esr

    return RippleDecomposition(
        output_vpp_v=peak_to_peak(vout),
        capacitor_internal_vpp_v=peak_to_peak(cap),
        esr_vpp_v=peak_to_peak(esr),
        reconstruction_mae_v=float(np.mean(np.abs(residual))),
        reconstruction_rmse_v=float(np.sqrt(np.mean(residual * residual))),
        reconstruction_max_abs_v=float(np.max(np.abs(residual))),
        sample_count=int(time.size),
        start_time_s=float(time[0]),
        end_time_s=float(time[-1]),
    )


def theoretical_ripple_components(
    inductor_ripple_a: float,
    switching_frequency_hz: float,
    capacitance_f: float,
    esr_ohm: float,
) -> dict[str, Any]:
    """理想 CCM 三角波近似下的纹波参考值（``analytical_theory``）。

    只用于对照，不替换真实 SPICE 纹波，也不把两个峰峰值直接相加当作实际纹波。
    """
    delta_i = abs(float(inductor_ripple_a))
    frequency = float(switching_frequency_hz)
    capacitance = float(capacitance_f)
    esr = float(esr_ohm)
    if frequency <= 0 or capacitance <= 0 or esr < 0:
        raise ValueError("frequency and capacitance must be positive, ESR nonnegative")
    cap_ripple = delta_i / (8.0 * frequency * capacitance)
    esr_ripple = delta_i * esr
    return {
        "inductor_ripple_a": delta_i,
        "capacitor_voltage_ripple_vpp": cap_ripple,
        "esr_voltage_ripple_vpp": esr_ripple,
        "note": (
            "ideal triangular-current CCM approximation; theoretical reference only, "
            "not a substitute for the simulated output ripple"
        ),
        "data_source": "analytical_theory",
    }

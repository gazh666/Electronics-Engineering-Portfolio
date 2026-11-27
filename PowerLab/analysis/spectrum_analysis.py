"""频谱分析：重采样、幅值谱、功率谱密度与可信频段。

原则：

- 原始 SPICE 波形非均匀采样，FFT 前必须显式重采样，过程记录在 ``ResampleInfo``；
- 重采样只做线性插值，不生成任何"猜测波形"；
- 可信最高频率取 ``min(fs/2, 0.5/最大原始采样间隔)``，超过它的谐波标记 NOT_RESOLVED；
- 默认使用 Hann 窗并做相干增益补偿；矩形窗仅用于对照。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.signal import get_window, periodogram

from .time_domain import time_step_statistics, validate_time_series

SUPPORTED_WINDOWS = ("hann", "boxcar", "hamming", "blackman")


@dataclass(frozen=True)
class ResampleInfo:
    original_points: int
    resampled_points: int
    sample_rate_hz: float
    nyquist_hz: float
    frequency_resolution_hz: float
    median_step_s: float
    max_step_s: float
    trusted_max_hz: float
    window_start_s: float
    window_end_s: float
    complete_cycles: int
    interpolation: str = "linear"

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_points": self.original_points,
            "resampled_points": self.resampled_points,
            "sample_rate_hz": self.sample_rate_hz,
            "nyquist_hz": self.nyquist_hz,
            "frequency_resolution_hz": self.frequency_resolution_hz,
            "median_step_s": self.median_step_s,
            "max_step_s": self.max_step_s,
            "trusted_max_hz": self.trusted_max_hz,
            "window_start_s": self.window_start_s,
            "window_end_s": self.window_end_s,
            "complete_cycles": self.complete_cycles,
            "interpolation": self.interpolation,
        }


@dataclass(frozen=True)
class SpectrumResult:
    frequency_hz: np.ndarray
    amplitude_peak: np.ndarray
    amplitude_rms: np.ndarray
    psd: np.ndarray
    amplitude_dbv: np.ndarray
    dc_value: float
    window_name: str
    resample: ResampleInfo
    data_source: str = "spice_derived"
    resampled_values: np.ndarray | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frequency_hz": self.frequency_hz.tolist(),
            "amplitude_peak": self.amplitude_peak.tolist(),
            "amplitude_rms": self.amplitude_rms.tolist(),
            "psd": self.psd.tolist(),
            "amplitude_dbv": self.amplitude_dbv.tolist(),
            "dc_value": self.dc_value,
            "window_name": self.window_name,
            "resample": self.resample.to_dict(),
            "method": "linear_resample_plus_windowed_rfft",
            "note": (
                "linear interpolation attenuates components near the Nyquist limit; "
                "frequency content above trusted_max_hz is not reported as resolved"
            ),
            "data_source": self.data_source,
        }

    def metadata(self) -> dict[str, Any]:
        """不含大数组的摘要，便于写入 JSON。"""
        return {
            "frequency_resolution_hz": self.resample.frequency_resolution_hz,
            "nyquist_hz": self.resample.nyquist_hz,
            "trusted_max_hz": self.resample.trusted_max_hz,
            "sample_rate_hz": self.resample.sample_rate_hz,
            "resampled_points": self.resample.resampled_points,
            "complete_cycles": self.resample.complete_cycles,
            "window_name": self.window_name,
            "dc_value": self.dc_value,
            "data_source": self.data_source,
        }

    def amplitude_at(self, frequency_hz: float) -> float:
        """返回最近频点的幅度（峰值）。"""
        index = int(np.argmin(np.abs(self.frequency_hz - float(frequency_hz))))
        return float(self.amplitude_peak[index])


def choose_sample_rate(
    duration_s: float,
    switching_frequency_hz: float,
    samples_per_cycle: int,
    maximum_samples: int,
) -> tuple[float, int]:
    """根据每周期采样点、窗口长度与样本上限选择采样率与点数。"""
    duration = float(duration_s)
    frequency = float(switching_frequency_hz)
    per_cycle = int(samples_per_cycle)
    limit = int(maximum_samples)
    if duration <= 0 or frequency <= 0 or per_cycle < 8:
        raise ValueError("invalid spectrum sampling parameters")
    if limit < 1024:
        raise ValueError("maximum_samples must be at least 1024")
    sample_rate = frequency * per_cycle
    point_count = int(np.floor(duration * sample_rate))
    if point_count > limit:
        point_count = limit
        sample_rate = point_count / duration
    if point_count < 1024:
        raise ValueError("steady window is too short for a reliable spectrum")
    return float(sample_rate), int(point_count)


def resample_uniform(
    time_s: Any,
    values: Any,
    *,
    start_s: float,
    end_s: float,
    sample_rate_hz: float,
    point_count: int,
) -> tuple[np.ndarray, np.ndarray, ResampleInfo]:
    """在指定窗口内把非均匀波形线性重采样为均匀序列。"""
    time, array = validate_time_series(time_s, values)
    start = float(start_s)
    end = float(end_s)
    if end <= start:
        raise ValueError("invalid resample window")
    if start < float(time[0]) - 1e-15 or end > float(time[-1]) + 1e-15:
        raise ValueError("resample window outside data range")
    sample_rate = float(sample_rate_hz)
    count = int(point_count)
    if sample_rate <= 0 or count < 2:
        raise ValueError("invalid sampling parameters")

    uniform_time = start + np.arange(count, dtype=float) / sample_rate
    if uniform_time[-1] > end + 1e-18:
        raise ValueError("sample grid exceeds requested window")
    uniform_values = np.interp(uniform_time, time, array)

    statistics = time_step_statistics(time[(time >= start) & (time <= end)])
    nyquist = sample_rate / 2.0
    trusted = min(nyquist, 0.5 / statistics["max_step_s"])
    # 完整周期数需要开关频率，由 analyze_spectrum 在拿到频率后回填。
    complete_cycles = 0
    info = ResampleInfo(
        original_points=int(time.size),
        resampled_points=count,
        sample_rate_hz=sample_rate,
        nyquist_hz=float(nyquist),
        frequency_resolution_hz=float(sample_rate / count),
        median_step_s=float(statistics["median_step_s"]),
        max_step_s=float(statistics["max_step_s"]),
        trusted_max_hz=float(trusted),
        window_start_s=float(uniform_time[0]),
        window_end_s=float(uniform_time[-1]),
        complete_cycles=complete_cycles,
    )
    return uniform_time, uniform_values, info


def analyze_spectrum(
    time_s: Any,
    values: Any,
    *,
    start_s: float,
    end_s: float,
    switching_frequency_hz: float,
    samples_per_cycle: int = 200,
    window_name: str = "hann",
    maximum_samples: int = 1_000_000,
) -> SpectrumResult:
    """完整频谱流程：选择采样率 → 重采样 → 加窗 → rfft → 幅值/PSD。"""
    if window_name not in SUPPORTED_WINDOWS:
        raise ValueError(f"unsupported window: {window_name}")
    duration = float(end_s) - float(start_s)
    sample_rate, count = choose_sample_rate(
        duration, switching_frequency_hz, samples_per_cycle, maximum_samples
    )
    uniform_time, uniform_values, info = resample_uniform(
        time_s,
        values,
        start_s=start_s,
        end_s=end_s,
        sample_rate_hz=sample_rate,
        point_count=count,
    )
    info = _with_cycle_count(info, switching_frequency_hz)

    dc_value = float(np.mean(uniform_values))
    signal = uniform_values - dc_value
    window = get_window(window_name, count, fftbins=True)
    coherent_gain = float(np.mean(window))
    transformed = np.fft.rfft(signal * window)
    frequency = np.fft.rfftfreq(count, d=1.0 / sample_rate)
    amplitude_peak = np.abs(transformed) * 2.0 / (count * coherent_gain)
    amplitude_peak[0] /= 2.0
    amplitude_peak[-1] /= 2.0
    amplitude_rms = amplitude_peak / np.sqrt(2.0)
    with np.errstate(divide="ignore"):
        amplitude_dbv = 20.0 * np.log10(np.maximum(amplitude_rms, 1e-30))
    _, psd = periodogram(
        uniform_values,
        fs=sample_rate,
        window=window_name,
        detrend="constant",
        scaling="density",
    )
    if psd.size != frequency.size:
        raise ValueError("spectrum length mismatch")

    return SpectrumResult(
        frequency_hz=frequency,
        amplitude_peak=amplitude_peak,
        amplitude_rms=amplitude_rms,
        psd=psd,
        amplitude_dbv=amplitude_dbv,
        dc_value=dc_value,
        window_name=window_name,
        resample=info,
        resampled_values=uniform_values,
    )


def _with_cycle_count(info: ResampleInfo, switching_frequency_hz: float) -> ResampleInfo:
    duration = info.window_end_s - info.window_start_s + 1.0 / info.sample_rate_hz
    cycles = int(np.floor(duration * float(switching_frequency_hz) + 1e-9))
    return ResampleInfo(
        original_points=info.original_points,
        resampled_points=info.resampled_points,
        sample_rate_hz=info.sample_rate_hz,
        nyquist_hz=info.nyquist_hz,
        frequency_resolution_hz=info.frequency_resolution_hz,
        median_step_s=info.median_step_s,
        max_step_s=info.max_step_s,
        trusted_max_hz=info.trusted_max_hz,
        window_start_s=info.window_start_s,
        window_end_s=info.window_end_s,
        complete_cycles=cycles,
    )

"""频率响应分析：传递函数、Bode 指标、截止频率与谐振峰。

截止频率与峰值频率必须从实际仿真数组插值得到，
不能把理论公式值冒充为"仿真截止频率"。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

DEFAULT_CUTOFF_LEVEL_RATIO = 1.0 / math.sqrt(2.0)
DEFAULT_CUTOFF_LEVEL_DB = -3.010299956639812


def _complex_pair(vin: Any, vout: Any) -> tuple[np.ndarray, np.ndarray]:
    vin_array = np.asarray(vin, dtype=complex)
    vout_array = np.asarray(vout, dtype=complex)
    if vin_array.shape != vout_array.shape:
        raise ValueError(f"waveform shape mismatch: vin {vin_array.shape} vs vout {vout_array.shape}")
    if vin_array.size == 0:
        raise ValueError("input waveforms must not be empty")
    if not np.isfinite(vin_array.real).all() or not np.isfinite(vin_array.imag).all():
        raise ValueError("invalid input waveform")
    if not np.isfinite(vout_array.real).all() or not np.isfinite(vout_array.imag).all():
        raise ValueError("invalid output waveform")
    if np.any(np.abs(vin_array) == 0):
        raise ValueError("zero AC input amplitude makes the transfer function undefined")
    return vin_array, vout_array


def gain_to_db(magnitude: Any) -> np.ndarray:
    """20log10(|H|)；幅值为 0 时返回 ``-inf``（派生指标的数学边界）。"""
    values = np.asarray(magnitude, dtype=float)
    if values.size == 0:
        raise ValueError("magnitude must not be empty")
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("magnitude must be finite and nonnegative")
    result = np.full(values.shape, -np.inf, dtype=float)
    positive = values > 0
    result[positive] = 20.0 * np.log10(values[positive])
    return result


def calculate_frequency_response(vin: Any, vout: Any) -> dict[str, Any]:
    """计算 H = Vout/Vin、幅值、dB 增益与相位（度）。"""
    vin_array, vout_array = _complex_pair(vin, vout)
    transfer = vout_array / vin_array
    magnitude = np.abs(transfer)
    return {
        "transfer": transfer,
        "magnitude": magnitude,
        "gain_db": gain_to_db(magnitude),
        "phase_deg": np.angle(transfer, deg=True),
        "zero_magnitude_count": int(np.count_nonzero(magnitude == 0)),
        "data_source": "derived_from_spice_simulation",
    }


def _validate_axis(frequency_hz: Any, values: Any) -> tuple[np.ndarray, np.ndarray]:
    frequency = np.asarray(frequency_hz, dtype=float)
    value_array = np.asarray(values, dtype=float)
    if frequency.shape != value_array.shape:
        raise ValueError("frequency and values must have the same shape")
    if frequency.ndim != 1 or frequency.size < 2:
        raise ValueError("frequency axis must be 1D with at least two samples")
    if not np.isfinite(frequency).all() or np.any(frequency <= 0):
        raise ValueError("frequency axis must be finite and positive")
    if not np.all(np.diff(frequency) > 0):
        raise ValueError("frequency axis must be strictly increasing")
    if not np.isfinite(value_array).all():
        raise ValueError("values contain NaN or Infinity")
    return frequency, value_array


def interpolate_crossing_log_frequency(
    frequency_hz: Any,
    values: Any,
    level: float,
) -> dict[str, Any]:
    """在 log10(f) 上线性插值，求 ``values`` 首次向下穿过 ``level`` 的频率。

    适用于单调下降的幅频或增益曲线；找不到交点时返回 ``found=False``，
    不返回猜测值。
    """
    frequency, value_array = _validate_axis(frequency_hz, values)
    level = float(level)
    if not math.isfinite(level):
        raise ValueError("level must be finite")

    if value_array[0] <= level:
        return {
            "found": False,
            "reason": "curve is already at or below the level at the first sample",
            "level": level,
        }

    for index in range(1, frequency.size):
        high = value_array[index - 1]
        low = value_array[index]
        if high > level >= low:
            fraction = (level - high) / (low - high)
            log_frequency = math.log10(frequency[index - 1]) + fraction * (
                math.log10(frequency[index]) - math.log10(frequency[index - 1])
            )
            return {
                "found": True,
                "frequency_hz": float(10.0**log_frequency),
                "level": level,
                "lower_hz": float(frequency[index - 1]),
                "upper_hz": float(frequency[index]),
                "lower_value": float(high),
                "upper_value": float(low),
                "method": "linear interpolation in log10(frequency)",
            }

    return {
        "found": False,
        "reason": "curve never crosses the level within the simulated band",
        "level": level,
    }


def estimate_cutoff_frequency(
    frequency_hz: Any,
    magnitude: Any,
    *,
    level_ratio: float = DEFAULT_CUTOFF_LEVEL_RATIO,
) -> dict[str, Any]:
    """由实际幅值曲线估计截止频率（默认 -3.0103 dB / 0.7071 幅值）。"""
    if not 0 < level_ratio < 1:
        raise ValueError("level_ratio must be in (0, 1)")
    result = interpolate_crossing_log_frequency(frequency_hz, magnitude, level_ratio)
    result["level_ratio"] = level_ratio
    result["level_db"] = 20.0 * math.log10(level_ratio)
    return result


def estimate_cutoff_frequency_from_gain(
    frequency_hz: Any,
    gain_db: Any,
    *,
    level_db: float = DEFAULT_CUTOFF_LEVEL_DB,
) -> dict[str, Any]:
    """由实际 dB 增益曲线估计截止频率。"""
    result = interpolate_crossing_log_frequency(frequency_hz, gain_db, level_db)
    result["level_db"] = level_db
    return result


def peak_metrics(frequency_hz: Any, values: Any) -> dict[str, Any]:
    """返回实际曲线的峰值及其频率；端点最大值不视为内部谐振峰。"""
    frequency, value_array = _validate_axis(frequency_hz, values)
    index = int(np.argmax(value_array))
    return {
        "peak_value": float(value_array[index]),
        "peak_frequency_hz": float(frequency[index]),
        "is_interior_peak": bool(0 < index < frequency.size - 1),
        "index": index,
    }


def resonance_peak(frequency_hz: Any, magnitude: Any) -> dict[str, Any]:
    """谐振峰（幅值最大值）；高阻尼无内部峰值时 ``is_interior_peak=False``。"""
    result = peak_metrics(frequency_hz, magnitude)
    result["found_interior_peak"] = result["is_interior_peak"]
    return result


def phase_unwrap(phase_deg: Any) -> np.ndarray:
    """相位展开（度），便于观察连续相频曲线。"""
    phase = np.asarray(phase_deg, dtype=float)
    if phase.size == 0:
        raise ValueError("phase array must not be empty")
    if not np.isfinite(phase).all():
        raise ValueError("phase array contains NaN or Infinity")
    return np.degrees(np.unwrap(np.radians(phase)))


def sanitize_for_json(value: Any) -> Any:
    """把非有限浮点数转换成清晰的字符串标记，保证标准 JSON 可序列化。

    ``-inf`` → ``"-Infinity"``，``inf`` → ``"Infinity"``，``nan`` → ``"NaN"``。
    """
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return [sanitize_for_json(item) for item in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)

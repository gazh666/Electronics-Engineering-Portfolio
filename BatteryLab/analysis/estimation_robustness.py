"""算法鲁棒性实验工具与 S01–S24 预注册矩阵（Task 18 / Task 33）。

这些扰动都是**人工研究扰动**，不是真实芯片的生产分布，也不能描述为真实硬件
故障。对公开实验数据施加扰动时，原始电流仍用于建立参考 SOC 轨迹，只有扰动
后的电流进入估计器；结果类型标记为 ``public_data_with_synthetic_sensor_error``。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from sensing.adc import adc_convert

SCENARIOS: tuple[dict[str, str], ...] = (
    {"id": "S01", "experiment": "正确初始SOC", "category": "initial_soc", "expected": "PASS"},
    {"id": "S02", "experiment": "初始SOC偏低10个百分点", "category": "initial_soc", "expected": "PASS"},
    {"id": "S03", "experiment": "初始SOC偏高10个百分点", "category": "initial_soc", "expected": "PASS"},
    {"id": "S04", "experiment": "初始SOC偏低20个百分点", "category": "initial_soc", "expected": "PASS"},
    {"id": "S05", "experiment": "初始SOC偏高20个百分点", "category": "initial_soc", "expected": "PASS"},
    {"id": "S06", "experiment": "电流固定失调", "category": "current_sensor", "expected": "PASS"},
    {"id": "S07", "experiment": "电流增益偏差", "category": "current_sensor", "expected": "PASS"},
    {"id": "S08", "experiment": "电流随机噪声", "category": "current_sensor", "expected": "PASS"},
    {"id": "S09", "experiment": "ADC量化", "category": "current_sensor", "expected": "PASS"},
    {"id": "S10", "experiment": "电压采集失调", "category": "voltage_sensor", "expected": "PASS"},
    {"id": "S11", "experiment": "容量偏差", "category": "model_mismatch", "expected": "PASS"},
    {"id": "S12", "experiment": "R0偏差", "category": "model_mismatch", "expected": "PASS"},
    {"id": "S13", "experiment": "RC参数偏差", "category": "model_mismatch", "expected": "PASS"},
    {"id": "S14", "experiment": "OCV低斜率区", "category": "observability", "expected": "PASS"},
    {"id": "S15", "experiment": "静置校正条件不足", "category": "observability", "expected": "PASS"},
    {"id": "S16", "experiment": "数据缺失", "category": "data_quality", "expected": "PASS"},
    {"id": "S17", "experiment": "温度失配", "category": "temperature", "expected": "NOT_VERIFIED"},
    {"id": "S18", "experiment": "动态充放电切换", "category": "dynamics", "expected": "PASS"},
    {"id": "S19", "experiment": "3S初始SOC不一致", "category": "pack", "expected": "PASS"},
    {"id": "S20", "experiment": "3S容量不一致", "category": "pack", "expected": "PASS"},
    {"id": "S21", "experiment": "均衡支路电流补偿", "category": "pack", "expected": "PASS"},
    {"id": "S22", "experiment": "CC-CV充电SOC估计", "category": "charging", "expected": "PASS"},
    {"id": "S23", "experiment": "保护中断", "category": "charging", "expected": "PASS"},
    {"id": "S24", "experiment": "老化后容量更新", "category": "aging", "expected": "NOT_VERIFIED"},
)


def scenario_matrix() -> list[dict[str, Any]]:
    """返回 S01–S24 预注册矩阵副本（可追加执行结果）。"""
    return [dict(item, status="NOT_EXECUTED", note="") for item in SCENARIOS]


def inject_current_sensor_error(
    reference_current_a: Sequence[float],
    offset_a: float = 0.0,
    gain_error_percent: float = 0.0,
    noise_std_a: float = 0.0,
    seed: int = 42,
) -> np.ndarray:
    """对电流序列叠加固定失调、增益误差与白噪声。"""
    current = np.asarray(reference_current_a, dtype=float)
    if current.ndim != 1:
        raise ValueError("Invalid current waveform")
    if not np.isfinite(current).all():
        raise ValueError("Invalid current waveform")
    if not all(
        math.isfinite(float(value)) for value in (offset_a, gain_error_percent, noise_std_a)
    ):
        raise ValueError("Invalid sensor parameter")
    if float(noise_std_a) < 0.0:
        raise ValueError("Invalid noise")
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, float(noise_std_a), size=current.shape)
    return current * (1.0 + float(gain_error_percent) / 100.0) + float(offset_a) + noise


def quantize_current_measurement(
    reference_current_a: Sequence[float],
    *,
    shunt_ohm: float = 0.01,
    amplifier_gain: float = 50.0,
    reference_v: float = 1.65,
    adc_reference_v: float = 3.3,
    adc_bits: int = 12,
) -> np.ndarray:
    """模拟"分流电阻 + 放大器 + ADC"后的电流读数（中点重构）。"""
    current = np.asarray(reference_current_a, dtype=float)
    if current.ndim != 1 or not np.isfinite(current).all():
        raise ValueError("Invalid current waveform")
    if shunt_ohm <= 0.0 or amplifier_gain <= 0.0:
        raise ValueError("Invalid sensing gain")
    output_v = reference_v + amplifier_gain * shunt_ohm * current
    decoded = np.asarray(
        [
            adc_convert(float(value), reference_v=adc_reference_v, bits=adc_bits).decoded_voltage_v
            if 0.0 <= float(value) < adc_reference_v
            else (0.0 if float(value) < 0.0 else adc_reference_v)
            for value in output_v
        ],
        dtype=float,
    )
    return (decoded - reference_v) / (amplifier_gain * shunt_ohm)


def apply_voltage_offset(voltage_v: Sequence[float], offset_v: float) -> np.ndarray:
    values = np.asarray(voltage_v, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Invalid voltage waveform")
    if not math.isfinite(float(offset_v)):
        raise ValueError("Invalid offset")
    return values + float(offset_v)


def scale_parameter(value: float, deviation_percent: float) -> float:
    if not math.isfinite(float(value)) or not math.isfinite(float(deviation_percent)):
        raise ValueError("Invalid parameter")
    return float(value) * (1.0 + float(deviation_percent) / 100.0)


def capacity_deviation_percentages() -> list[float]:
    return [-20.0, -10.0, -5.0, 0.0, 5.0, 10.0]


def current_offset_scan_ma() -> list[float]:
    return [-20.0, -10.0, -5.0, 0.0, 5.0, 10.0, 20.0]


def current_gain_scan_percent() -> list[float]:
    return [-1.0, -0.5, 0.0, 0.5, 1.0]


def current_noise_scan_ma() -> list[float]:
    return [0.0, 2.0, 5.0, 10.0]

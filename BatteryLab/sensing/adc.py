"""通用教学 ADC 行为模型（Task 17/18/19）。

统一采用中点重构约定：

    LSB = Vref / 2**N
    code = floor(Vin / LSB)           # 限制在 0 .. 2**N-1
    Vdecoded = (code + 0.5) * LSB

数据来源标记为 ``adc_behavioral_model``。本模型不是任何真实芯片的转换精度
测量，也不把标称分辨率描述为有效精度（ENOB）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


class ADCError(ValueError):
    """ADC 输入非法。"""


@dataclass(frozen=True)
class ADCConfig:
    reference_voltage_v: float = 3.3
    resolution_bits: int = 12
    input_min_v: float = 0.0
    data_source: str = "adc_behavioral_model"

    def __post_init__(self) -> None:
        if not math.isfinite(self.reference_voltage_v) or self.reference_voltage_v <= 0.0:
            raise ADCError("参考电压必须为有限正数")
        if isinstance(self.resolution_bits, bool) or not isinstance(self.resolution_bits, int):
            raise ADCError("分辨率必须是整数")
        if not 4 <= self.resolution_bits <= 24:
            raise ADCError("分辨率必须位于 [4, 24]")
        if not math.isfinite(self.input_min_v) or self.input_min_v < 0.0:
            raise ADCError("ADC 输入下限必须为非负有限值")

    @property
    def levels(self) -> int:
        return 2**self.resolution_bits

    @property
    def lsb_v(self) -> float:
        return self.reference_voltage_v / self.levels


@dataclass(frozen=True)
class ADCSample:
    input_voltage_v: float
    code: int
    decoded_voltage_v: float
    lsb_v: float
    saturated_low: bool
    saturated_high: bool

    @property
    def saturated(self) -> bool:
        return self.saturated_low or self.saturated_high

    @property
    def quantization_error_v(self) -> float | None:
        if self.saturated:
            return None
        return self.decoded_voltage_v - self.input_voltage_v


def adc_lsb(config: ADCConfig | None = None, *, reference_v: float | None = None, bits: int | None = None) -> float:
    if config is not None:
        return config.lsb_v
    if reference_v is None or bits is None:
        raise ADCError("必须提供 config，或同时提供 reference_v 与 bits")
    return float(reference_v) / (2**int(bits))


def adc_convert(
    voltage_v: float,
    config: ADCConfig | None = None,
    *,
    reference_v: float = 3.3,
    bits: int = 12,
    input_min_v: float = 0.0,
) -> ADCSample:
    """按中点重构约定转换单点电压。"""
    active = config or ADCConfig(reference_v, bits, input_min_v)
    if not math.isfinite(voltage_v):
        raise ADCError("ADC 输入必须是有限数值")
    lsb = active.lsb_v
    levels = active.levels
    saturated_low = voltage_v < active.input_min_v
    saturated_high = voltage_v >= active.reference_voltage_v
    raw_code = math.floor((voltage_v - active.input_min_v) / lsb)
    code = min(max(raw_code, 0), levels - 1)
    decoded = active.input_min_v + (code + 0.5) * lsb
    return ADCSample(
        input_voltage_v=float(voltage_v),
        code=int(code),
        decoded_voltage_v=float(decoded),
        lsb_v=float(lsb),
        saturated_low=bool(saturated_low),
        saturated_high=bool(saturated_high),
    )


def adc_convert_sequence(voltages: Sequence[float], config: ADCConfig | None = None) -> list[ADCSample]:
    return [adc_convert(value, config) for value in voltages]


def check_monotonic(voltages: Sequence[float], config: ADCConfig | None = None) -> bool:
    """码值必须随输入单调不减。"""
    samples = adc_convert_sequence(voltages, config)
    codes = [sample.code for sample in samples]
    return all(later >= earlier for earlier, later in zip(codes, codes[1:]))


@dataclass(frozen=True)
class ADCErrorModel:
    """ADC 非理想项。

    ``reference_deviation_v`` 为实际参考相对标称参考的偏差；真实编码使用
    ``reference + deviation``，软件解码使用标称参考，因此不会自相抵消。
    """

    reference_deviation_v: float = 0.0
    input_offset_v: float = 0.0
    gain_error_fraction: float = 0.0
    noise_rms_v: float = 0.0
    inl_lsb: float = 0.0
    random_seed: int = 42

    def __post_init__(self) -> None:
        for name in (
            "reference_deviation_v",
            "input_offset_v",
            "gain_error_fraction",
            "noise_rms_v",
            "inl_lsb",
        ):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ADCError(f"{name} 必须为有限值")
        if self.noise_rms_v < 0.0:
            raise ADCError("噪声 RMS 不能为负")


def adc_convert_real(
    voltage_v: float,
    config: ADCConfig,
    errors: ADCErrorModel,
    rng: np.random.Generator | None = None,
) -> ADCSample:
    """包含参考偏差、失调、增益、噪声与 INL 的真实编码；软件按标称参考解码。"""
    if not math.isfinite(voltage_v):
        raise ADCError("ADC 输入必须是有限数值")
    generator = rng or np.random.default_rng(errors.random_seed)
    lsb_nominal = config.lsb_v

    conditioned = voltage_v * (1.0 + errors.gain_error_fraction) + errors.input_offset_v
    # INL 作为确定性非线性，叠加在量化前电压上（教学近似）
    if errors.inl_lsb:
        phase = (voltage_v / config.reference_voltage_v) * 2.0 * math.pi
        conditioned += errors.inl_lsb * lsb_nominal * 0.5 * math.sin(phase)
    if errors.noise_rms_v:
        conditioned += float(generator.normal(0.0, errors.noise_rms_v))

    actual_reference = config.reference_voltage_v + errors.reference_deviation_v
    lsb_actual = actual_reference / config.levels
    raw_code = math.floor((conditioned - config.input_min_v) / lsb_actual)
    code = min(max(raw_code, 0), config.levels - 1)
    # 软件使用标称参考恢复电压（不抵消误差）
    decoded_nominal = config.input_min_v + (code + 0.5) * lsb_nominal
    saturated_low = conditioned < config.input_min_v
    saturated_high = conditioned >= actual_reference
    sample = ADCSample(
        input_voltage_v=float(voltage_v),
        code=int(code),
        decoded_voltage_v=float(decoded_nominal),
        lsb_v=float(lsb_nominal),
        saturated_low=bool(saturated_low),
        saturated_high=bool(saturated_high),
    )
    return sample


def quantization_staircase(
    start_v: float,
    stop_v: float,
    points: int,
    config: ADCConfig | None = None,
) -> dict[str, np.ndarray]:
    """生成量化阶梯曲线与量化误差。"""
    if points < 2:
        raise ADCError("采样点至少为 2")
    voltages = np.linspace(float(start_v), float(stop_v), int(points))
    samples = adc_convert_sequence(voltages, config)
    return {
        "input_v": voltages,
        "code": np.array([sample.code for sample in samples], dtype=int),
        "decoded_v": np.array([sample.decoded_voltage_v for sample in samples], dtype=float),
        "error_v": np.array(
            [sample.quantization_error_v if sample.quantization_error_v is not None else np.nan for sample in samples],
            dtype=float,
        ),
        "saturated": np.array([sample.saturated for sample in samples], dtype=bool),
    }


def theoretical_lsb_input_referred(config: ADCConfig, analog_gain: float) -> float:
    """把 ADC 量化步距折算到被测输入端。"""
    if not math.isfinite(analog_gain) or analog_gain == 0.0:
        raise ADCError("模拟增益必须为非零有限值")
    return config.lsb_v / abs(analog_gain)


def compare_resolutions(
    reference_v: float = 3.3,
    bits: Iterable[int] = (10, 12, 16),
) -> list[dict[str, float]]:
    rows = []
    for value in bits:
        config = ADCConfig(reference_v, int(value))
        rows.append(
            {
                "bits": int(value),
                "levels": config.levels,
                "lsb_v": config.lsb_v,
                "input_referred_lsb_gain_0p5_v": config.lsb_v / 0.5,
                "input_referred_lsb_gain_50_v": config.lsb_v / 50.0,
            }
        )
    return rows

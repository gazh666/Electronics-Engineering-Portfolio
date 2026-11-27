"""ADC 行为模型测试（Task 17/18/19/36）。"""

from __future__ import annotations

import numpy as np
import pytest

from sensing.adc import (
    ADCConfig,
    ADCError,
    ADCErrorModel,
    adc_convert,
    adc_convert_real,
    adc_lsb,
    check_monotonic,
    quantization_staircase,
    theoretical_lsb_input_referred,
)


def test_lsb_12bit_3v3():
    config = ADCConfig(3.3, 12)
    assert config.levels == 4096
    assert config.lsb_v == pytest.approx(3.3 / 4096.0, rel=1e-12)
    assert adc_lsb(reference_v=3.3, bits=12) == pytest.approx(config.lsb_v)


@pytest.mark.parametrize(
    ("reference_v", "bits"),
    [(3.3, 10), (3.3, 12), (5.0, 16)],
)
def test_midpoint_quantization_error_bounded_by_half_lsb(reference_v, bits):
    config = ADCConfig(reference_v, bits)
    for value in np.linspace(0.0, reference_v * 0.999, 2000):
        sample = adc_convert(float(value), config)
        assert sample.code >= 0
        assert sample.code <= config.levels - 1
        assert abs(sample.decoded_voltage_v - value) <= 0.5 * config.lsb_v + 1e-12
        assert sample.quantization_error_v is not None


def test_saturation_flags_and_no_quantization_error():
    config = ADCConfig(3.3, 12)
    low = adc_convert(-1e-3, config)
    high = adc_convert(3.3, config)
    assert low.saturated_low and low.code == 0
    assert high.saturated_high and high.code == config.levels - 1
    assert low.quantization_error_v is None
    assert high.quantization_error_v is None


def test_monotonic_codes():
    config = ADCConfig(3.3, 12)
    assert check_monotonic(np.linspace(0.0, 3.4, 5000), config)


def test_reference_deviation_does_not_cancel():
    config = ADCConfig(3.3, 12)
    errors = ADCErrorModel(reference_deviation_v=0.003)
    sample = adc_convert_real(1.0, config, errors)
    # 软件仍按 3.3 V 解码，实际参考 3.303 V，读数应偏低约 0.09%
    assert -1.3e-3 < sample.quantization_error_v < -0.3e-3


def test_input_offset_shifts_reading():
    config = ADCConfig(3.3, 12)
    errors = ADCErrorModel(input_offset_v=0.01)
    sample = adc_convert_real(2.0, config, errors)
    assert sample.decoded_voltage_v == pytest.approx(2.01, abs=1.5e-3)


def test_noise_is_seeded_and_reproducible():
    config = ADCConfig(3.3, 12)
    errors = ADCErrorModel(noise_rms_v=2e-4, random_seed=7)
    first = adc_convert_real(1.5, config, errors)
    second = adc_convert_real(1.5, config, errors)
    assert first.code == second.code


def test_quantization_staircase_shapes():
    config = ADCConfig(3.3, 12)
    data = quantization_staircase(0.0, 3.3, 2000, config)
    assert data["input_v"].shape == (2000,)
    assert np.all(np.diff(data["code"]) >= 0)
    finite = data["error_v"][np.isfinite(data["error_v"])]
    assert np.max(np.abs(finite)) <= 0.5 * config.lsb_v + 1e-12


def test_input_referred_lsb_scales_with_gain():
    config = ADCConfig(3.3, 12)
    assert theoretical_lsb_input_referred(config, 0.5) == pytest.approx(config.lsb_v / 0.5)
    assert theoretical_lsb_input_referred(config, -50.0) == pytest.approx(config.lsb_v / 50.0)


@pytest.mark.parametrize("bits", [3, 25])
def test_invalid_resolution_rejected(bits):
    with pytest.raises(ADCError):
        ADCConfig(3.3, bits)


def test_non_finite_input_rejected():
    with pytest.raises(ADCError):
        adc_convert(float("nan"), ADCConfig())

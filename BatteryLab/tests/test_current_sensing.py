"""双向电流采集解析测试（Task 13/15/16/36）。"""

from __future__ import annotations

import pytest

from circuits.current_sensing import CurrentSensingError, CurrentSenseConfig
from scripts.stage4_common import current_sense_config
from sensing.current_decoder import (
    CurrentDecodeError,
    amplifier_output,
    current_from_output,
    current_resolution_a,
    full_scale_output_range,
    offset_referred_current_a,
    shunt_power,
    shunt_voltage,
)


@pytest.fixture()
def config() -> CurrentSenseConfig:
    return current_sense_config()


def test_nominal_parameters(config):
    assert config.shunt_ohm == pytest.approx(0.01)
    assert config.amplifier_gain == pytest.approx(50.0)
    assert config.reference_v == pytest.approx(1.65)


def test_bidirectional_output(config):
    assert config.output(0.0) == pytest.approx(1.65, abs=1e-12)
    assert config.output(2.5) == pytest.approx(2.90, abs=1e-12)
    assert config.output(-2.5) == pytest.approx(0.40, abs=1e-12)


def test_shunt_drop_and_power_at_2p5a(config):
    assert shunt_voltage(2.5, config.shunt_ohm) == pytest.approx(0.025, rel=1e-12)
    assert shunt_power(2.5, config.shunt_ohm) == pytest.approx(0.0625, rel=1e-12)
    assert shunt_power(-2.5, config.shunt_ohm) == pytest.approx(0.0625, rel=1e-12)


@pytest.mark.parametrize("current_a", [-3.0, -1.0, 0.0, 1.0, 3.0])
def test_current_round_trip(config, current_a):
    output = config.output(current_a)
    recovered = current_from_output(
        output,
        gain=config.amplifier_gain,
        shunt_ohm=config.shunt_ohm,
        reference_v=config.reference_v,
    )
    assert recovered == pytest.approx(current_a, abs=1e-12)


def test_adc_current_resolution(config):
    resolution = current_resolution_a(gain=50.0, shunt_ohm=0.01, lsb_v=3.3 / 4096)
    assert resolution == pytest.approx(3.3 / 4096 / 0.5, rel=1e-12)
    assert resolution == pytest.approx(0.001611328, rel=1e-5)


def test_input_offset_referred_current():
    assert offset_referred_current_a(25e-6, 0.01) == pytest.approx(0.0025, rel=1e-12)


def test_full_scale_output_range(config):
    low, high = full_scale_output_range(
        gain=config.amplifier_gain,
        shunt_ohm=config.shunt_ohm,
        reference_v=config.reference_v,
        current_limit_a=2.5,
    )
    assert low == pytest.approx(0.40)
    assert high == pytest.approx(2.90)


def test_saturation_boundaries(config):
    assert config.output(-3.3) < config.amplifier_output_low_v
    assert config.output(2.5) <= config.amplifier_output_high_v
    assert amplifier_output(0.0, gain=50.0, shunt_ohm=0.01, reference_v=1.65) == pytest.approx(1.65)


@pytest.mark.parametrize("bad", [0.0, -0.01])
def test_invalid_shunt_rejected(bad):
    with pytest.raises(CurrentDecodeError):
        shunt_voltage(1.0, bad)


def test_invalid_config_rejected():
    with pytest.raises(CurrentSensingError):
        CurrentSenseConfig(shunt_ohm=0.0, amplifier_gain=50.0, reference_v=1.65)

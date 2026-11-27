"""NTC 温度采集解析测试（Task 21/23/36）。"""

from __future__ import annotations

import pytest

from sensing.temperature_decoder import (
    TemperatureDecodeError,
    divider_voltage,
    ntc_power_w,
    ntc_resistance,
    ntc_temperature,
    resistance_from_voltage,
    temperature_from_voltage,
    voltage_sensitivity_v_per_c,
)


def test_r25_is_10k():
    assert ntc_resistance(25.0) == pytest.approx(10_000.0, rel=1e-12)


def test_ntc_resistance_decreases_with_temperature():
    values = [ntc_resistance(t) for t in (0.0, 25.0, 60.0)]
    assert values[0] > values[1] > values[2]
    assert values[0] == pytest.approx(33_000, rel=0.15)


def test_divider_at_25c_is_half_excitation():
    resistance = ntc_resistance(25.0)
    assert divider_voltage(resistance) == pytest.approx(1.65, rel=1e-12)


@pytest.mark.parametrize("temperature_c", [0.0, 10.0, 25.0, 45.0, 60.0])
def test_temperature_voltage_round_trip(temperature_c):
    resistance = ntc_resistance(temperature_c)
    voltage = divider_voltage(resistance)
    recovered = temperature_from_voltage(voltage)
    assert recovered == pytest.approx(temperature_c, abs=1e-9)


def test_resistance_temperature_round_trip():
    for resistance in (5_000.0, 10_000.0, 20_000.0):
        temperature = ntc_temperature(resistance)
        assert ntc_resistance(temperature) == pytest.approx(resistance, rel=1e-9)


def test_sensitivity_negative_near_25c():
    sensitivity = voltage_sensitivity_v_per_c(25.0)
    assert sensitivity < 0.0
    assert abs(sensitivity) == pytest.approx(0.044, rel=0.2)


def test_self_heating_power_is_small():
    power = ntc_power_w(25.0)
    assert 0.0 < power < 1e-3


def test_open_and_short_voltage_cannot_be_inverted():
    with pytest.raises(TemperatureDecodeError):
        resistance_from_voltage(0.0)
    with pytest.raises(TemperatureDecodeError):
        resistance_from_voltage(3.3)


def test_invalid_temperature_rejected():
    with pytest.raises(TemperatureDecodeError):
        ntc_resistance(-273.15)
    with pytest.raises(TemperatureDecodeError):
        ntc_resistance(25.0, beta_k=0.0)

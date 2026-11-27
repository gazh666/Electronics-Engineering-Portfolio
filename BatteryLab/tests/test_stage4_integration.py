"""第四阶段集成测试：真实 ngspice 采集链路与状态机（Task 30/36）。"""

from __future__ import annotations

import pytest

from circuits.cell_voltage_sensing import solve_3s_sensing
from circuits.current_sensing import solve_current
from circuits.spice_utils import get_solve_count, reset_solve_counter
from sensing.adc import ADCConfig
from sensing.measurement_chain import measure_current, measure_temperature, measure_voltage
from sensing.models import (
    STATUS_COMMON_MODE_OUT_OF_RANGE,
    STATUS_SATURATED,
    STATUS_SENSOR_OPEN,
    STATUS_SENSOR_SHORT,
    STATUS_VALID,
)
from scripts.stage4_common import afe, amplifier_config, current_sense_config


def test_afe_config_is_consistent():
    config = afe()
    assert config["battery_pack"]["series_cells"] == 3
    assert config["adc"]["resolution_bits"] == 12
    assert config["cell_voltage"]["measurement_min_v"] == pytest.approx(2.5)
    assert config["cell_voltage"]["measurement_max_v"] == pytest.approx(4.25)
    amp = amplifier_config(config)
    assert amp.r2_ohm / amp.r1_ohm == pytest.approx(0.5)
    assert amp.reference_v == pytest.approx(0.2)


def test_real_spice_3s_differential_sensing():
    config = amplifier_config()
    reset_solve_counter()
    rows = solve_3s_sensing([3.6, 3.8, 4.0], config)
    assert get_solve_count() == 1
    assert len(rows) == 3
    for row in rows:
        assert abs(row["error_v"]) < 1e-4
    # 对地节点与差分电压必须区分：cell2 的输入上端是 7.4 V
    assert rows[1]["vhigh_v"] == pytest.approx(7.4)
    # 2.099104 V 与无滤波理论 2.1 V 的差即 47 Ω 输入滤波负载效应（约 0.9 mV）
    assert rows[1]["vout_v"] == pytest.approx(2.1, abs=2e-3)


def test_real_spice_bidirectional_current():
    config = current_sense_config()
    reset_solve_counter()
    positive = solve_current(1.0, config)
    negative = solve_current(-1.0, config)
    assert get_solve_count() == 2
    assert positive["vout_v"] == pytest.approx(2.15, abs=1e-4)
    assert negative["vout_v"] == pytest.approx(1.15, abs=1e-4)
    assert positive["error_v"] == pytest.approx(0.0, abs=1e-4)


def test_measure_voltage_valid_and_saturated():
    valid = measure_voltage(
        channel_name="cell1",
        reference_cell_v=3.7,
        analog_output_v=2.05,
        gain=0.5,
        reference_v=0.2,
        adc_config=ADCConfig(3.3, 12),
    )
    assert valid.status == STATUS_VALID
    assert valid.estimated_value == pytest.approx(3.7, abs=1e-3)

    saturated = measure_voltage(
        channel_name="cell1",
        reference_cell_v=5.0,
        analog_output_v=3.3,
        gain=0.5,
        reference_v=0.2,
        adc_config=ADCConfig(3.3, 12),
    )
    assert saturated.status == STATUS_SATURATED


def test_measure_voltage_common_mode_out_of_range():
    result = measure_voltage(
        channel_name="cell3",
        reference_cell_v=4.0,
        analog_output_v=2.2,
        gain=0.5,
        reference_v=0.2,
        adc_config=ADCConfig(3.3, 12),
        pin_common_mode_v=5.5,
        common_mode_min_v=0.0,
        common_mode_max_v=5.0,
    )
    assert result.status == STATUS_COMMON_MODE_OUT_OF_RANGE


def test_measure_current_directions_and_saturation():
    config = current_sense_config()
    positive = measure_current(
        channel_name="pack",
        reference_current_a=2.0,
        analog_output_v=config.output(2.0),
        amplifier_gain=config.amplifier_gain,
        shunt_ohm=config.shunt_ohm,
        zero_reference_v=config.reference_v,
        adc_config=ADCConfig(3.3, 12),
    )
    negative = measure_current(
        channel_name="pack",
        reference_current_a=-1.0,
        analog_output_v=config.output(-1.0),
        amplifier_gain=config.amplifier_gain,
        shunt_ohm=config.shunt_ohm,
        zero_reference_v=config.reference_v,
        adc_config=ADCConfig(3.3, 12),
    )
    saturated = measure_current(
        channel_name="pack",
        reference_current_a=3.5,
        analog_output_v=config.output(3.5),
        amplifier_gain=config.amplifier_gain,
        shunt_ohm=config.shunt_ohm,
        zero_reference_v=config.reference_v,
        adc_config=ADCConfig(3.3, 12),
    )
    assert positive.estimated_value == pytest.approx(2.0, abs=1e-3)
    assert negative.estimated_value == pytest.approx(-1.0, abs=1e-3)
    assert saturated.status == STATUS_SATURATED


def test_measure_temperature_valid_open_short():
    valid = measure_temperature(
        channel_name="ntc",
        reference_temperature_c=25.0,
        analog_output_v=1.65,
        adc_config=ADCConfig(3.3, 12),
    )
    opened = measure_temperature(
        channel_name="ntc",
        reference_temperature_c=None,
        analog_output_v=3.29,
        adc_config=ADCConfig(3.3, 12),
    )
    shorted = measure_temperature(
        channel_name="ntc",
        reference_temperature_c=None,
        analog_output_v=0.01,
        adc_config=ADCConfig(3.3, 12),
    )
    assert valid.status == STATUS_VALID
    assert valid.estimated_value == pytest.approx(25.0, abs=0.05)
    assert opened.status == STATUS_SENSOR_OPEN
    assert shorted.status == STATUS_SENSOR_SHORT
    assert opened.estimated_value is None and shorted.estimated_value is None

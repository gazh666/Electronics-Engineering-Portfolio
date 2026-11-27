"""单体差分电压采集解析测试（Task 6/7/9/36）。"""

from __future__ import annotations

import pytest

from circuits.differential_amplifier import DifferentialAmplifierConfig
from scripts.stage4_common import amplifier_config
from sensing.voltage_decoder import (
    VoltageDecodeError,
    amplifier_pin_common_mode,
    cell_voltage_from_output,
    four_resistor_output,
    input_common_mode,
    matched_output,
    output_saturated,
)


@pytest.fixture()
def config() -> DifferentialAmplifierConfig:
    return amplifier_config()


def test_nominal_gain_and_reference(config):
    assert config.nominal_gain == pytest.approx(0.5)
    assert config.output(3.6, 0.0) == pytest.approx(2.0, abs=1e-12)
    assert config.output(7.4, 3.6) == pytest.approx(2.1, abs=1e-12)
    assert config.output(11.4, 7.4) == pytest.approx(2.2, abs=1e-12)


def test_matched_four_resistor_equals_reference_plus_gain(config):
    for cell_v in (2.5, 3.6, 4.0, 4.25):
        expected = matched_output(cell_v, gain=0.5, reference_v=0.2)
        actual = four_resistor_output(
            cell_v,
            0.0,
            r1_ohm=config.r1_ohm,
            r2_ohm=config.r2_ohm,
            r3_ohm=config.r3_ohm,
            r4_ohm=config.r4_ohm,
            reference_v=config.reference_v,
        )
        assert actual == pytest.approx(expected, abs=1e-12)


def test_decode_round_trip(config):
    for cell_v in (2.5, 3.7, 4.25):
        output = config.output(cell_v, 0.0)
        recovered = cell_voltage_from_output(output, gain=0.5, reference_v=0.2)
        assert recovered == pytest.approx(cell_v, abs=1e-12)


def test_top_cell_pin_common_mode_below_supply(config):
    pins = amplifier_pin_common_mode(
        11.4,
        7.4,
        r1_ohm=config.r1_ohm,
        r2_ohm=config.r2_ohm,
        r3_ohm=config.r3_ohm,
        r4_ohm=config.r4_ohm,
        reference_v=config.reference_v,
    )
    assert pins["v_inp_v"] == pytest.approx(3.9333333333, rel=1e-9)
    assert pins["v_inm_v"] == pytest.approx(pins["v_inp_v"], abs=1e-9)
    assert pins["v_inp_v"] < config.supply_v
    assert pins["v_out_v"] == pytest.approx(2.2, abs=1e-12)


def test_battery_node_common_mode_is_not_pin_common_mode(config):
    pins = amplifier_pin_common_mode(
        11.4,
        7.4,
        r1_ohm=config.r1_ohm,
        r2_ohm=config.r2_ohm,
        r3_ohm=config.r3_ohm,
        r4_ohm=config.r4_ohm,
        reference_v=config.reference_v,
    )
    assert input_common_mode(11.4, 7.4) == pytest.approx(9.4)
    assert pins["v_inp_v"] < 4.0


def test_resistor_mismatch_changes_output(config):
    ideal = config.output(7.4, 3.6)
    mismatched = four_resistor_output(
        7.4,
        3.6,
        r1_ohm=config.r1_ohm * 1.01,
        r2_ohm=config.r2_ohm,
        r3_ohm=config.r3_ohm,
        r4_ohm=config.r4_ohm,
        reference_v=config.reference_v,
    )
    assert abs(mismatched - ideal) > 1e-4
    assert config.gain_mismatch_ratio == pytest.approx(1.0)


def test_ground_referenced_nodes_are_not_cell_voltages(config):
    # 直接用对地节点差证明：N2 对地 7.4 V 必须减去 N1 才是 cell2
    vcell2 = 7.4 - 3.6
    assert config.output(7.4, 0.0) != pytest.approx(config.output(vcell2, 0.0))


def test_output_saturation_check():
    assert output_saturated(0.0, low_v=0.05, high_v=4.95)
    assert output_saturated(5.0, low_v=0.05, high_v=4.95)
    assert not output_saturated(2.0, low_v=0.05, high_v=4.95)


@pytest.mark.parametrize("bad", [(0.0, 1.0), (-1.0, 0.0)])
def test_invalid_resistors_rejected(bad):
    r1, r3 = bad
    with pytest.raises(VoltageDecodeError):
        four_resistor_output(3.6, 0.0, r1_ohm=r1, r2_ohm=50_000.0, r3_ohm=r3, r4_ohm=50_000.0, reference_v=0.2)

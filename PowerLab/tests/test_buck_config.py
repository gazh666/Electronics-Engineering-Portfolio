"""Buck 配置加载与跨字段校验测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from circuits.buck_config import (
    DEFAULT_BUCK_CONFIG_PATH,
    BuckConfig,
    BuckParameters,
    SteadyStateConfig,
    TransientConfig,
    load_buck_config,
)
from circuits.pwm import PWMParameters
from circuits.switch_models import SwitchConfig


def _payload() -> dict:
    return yaml.safe_load(DEFAULT_BUCK_CONFIG_PATH.read_text(encoding="utf-8"))


def _write(tmp_path, payload: dict):
    path = tmp_path / "buck.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_load_default_buck_config():
    parameters = load_buck_config()
    assert isinstance(parameters, BuckParameters)
    assert parameters.circuit.input_voltage_v == pytest.approx(12.0)
    assert parameters.circuit.target_output_voltage_v == pytest.approx(5.0)
    assert parameters.circuit.switching_frequency_hz == pytest.approx(100e3)
    assert parameters.circuit.inductance_h == pytest.approx(47e-6)
    assert parameters.circuit.capacitance_f == pytest.approx(100e-6)
    assert parameters.circuit.load_resistance_ohm == pytest.approx(2.5)
    assert parameters.pwm.frequency_hz == pytest.approx(parameters.circuit.switching_frequency_hz)
    assert parameters.transient.step_time_s == pytest.approx(100e-9)
    assert parameters.transient.max_step_time_s == pytest.approx(50e-9)
    assert parameters.transient.end_time_s == pytest.approx(5e-3)
    assert parameters.steady_state.minimum_cycles == 20
    assert parameters.steady_state.comparison_cycles == 10
    assert parameters.minimum_steps_per_period == pytest.approx(200.0)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_buck_config(tmp_path / "missing.yaml")


def test_missing_field_raises(tmp_path):
    payload = _payload()
    del payload["circuit"]["inductance_h"]
    with pytest.raises(ValueError, match="inductance_h"):
        load_buck_config(_write(tmp_path, payload))


def test_missing_section_raises(tmp_path):
    payload = _payload()
    del payload["pwm"]
    with pytest.raises(ValueError, match="pwm"):
        load_buck_config(_write(tmp_path, payload))


def test_target_output_must_be_below_input():
    with pytest.raises(ValueError):
        BuckConfig(input_voltage_v=5.0, target_output_voltage_v=5.0)


@pytest.mark.parametrize("duty", [0.0, 1.0, -0.2])
def test_duty_cycle_must_be_inside_open_interval(duty):
    with pytest.raises(ValueError):
        BuckConfig(duty_cycle=duty)


def test_pwm_frequency_must_match_circuit():
    parameters = load_buck_config()
    mismatched = replace(parameters.pwm, frequency_hz=90e3)
    with pytest.raises(ValueError, match="frequency"):
        replace(parameters, pwm=mismatched)


def test_gate_levels_must_switch_the_model():
    parameters = load_buck_config()
    low_gate = replace(parameters.pwm, high_voltage_v=2.0)
    with pytest.raises(ValueError, match="turn-on"):
        replace(parameters, pwm=low_gate)


def test_pwm_delay_must_be_shorter_than_end_time():
    parameters = load_buck_config()
    late = replace(parameters.pwm, delay_s=parameters.transient.end_time_s)
    with pytest.raises(ValueError, match="delay"):
        replace(parameters, pwm=late)


def test_max_step_must_not_exceed_step_time():
    with pytest.raises(ValueError):
        TransientConfig(step_time_s=50e-9, max_step_time_s=100e-9)


def test_steady_state_needs_two_comparison_groups():
    with pytest.raises(ValueError):
        SteadyStateConfig(minimum_cycles=10, comparison_cycles=10)


def test_switch_requires_on_below_off():
    with pytest.raises(ValueError):
        SwitchConfig(on_resistance_ohm=10.0, off_resistance_ohm=1.0)


def test_pwm_config_alias_is_pwm_parameters():
    from circuits.buck_config import PWMConfig

    assert PWMConfig is PWMParameters


def test_parameters_snapshot_roundtrip():
    payload = load_buck_config().to_dict()
    assert payload["version"] == "1.0"
    assert payload["circuit"]["topology"] == "asynchronous_buck"
    assert payload["pwm"]["period_s"] == pytest.approx(10e-6)
    assert payload["simulation"]["required_minimum_steps_per_period"] == 20
    assert payload["steady_state"]["minimum_cycles"] == 20

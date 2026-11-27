"""第四阶段配置加载与校验测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from circuits.pwm import PWMParameters
from circuits.nonideal_config import (
    GateDriverConfig,
    MosfetModelConfig,
    load_device_models,
    load_nonideal_buck_config,
    load_validation_limits,
    temperature_values,
)


def test_load_nonideal_config_basics():
    config = load_nonideal_buck_config()
    assert config.input_voltage_v == pytest.approx(12.0)
    assert config.target_output_voltage_v == pytest.approx(5.0)
    assert config.switching_frequency_hz == pytest.approx(100e3)
    assert config.period_s == pytest.approx(1e-5)
    assert config.inductor.dcr_ohm == pytest.approx(0.05)
    assert config.capacitor.esr_ohm == pytest.approx(0.03)
    assert config.model_variant == "E"


def test_pwm_property_uses_floating_drive_level():
    config = load_nonideal_buck_config()
    pwm = config.pwm
    assert isinstance(pwm, PWMParameters)
    assert pwm.high_voltage_v == pytest.approx(config.gate_driver.drive_voltage_v)
    assert pwm.low_voltage_v == pytest.approx(0.0)
    assert pwm.duty_cycle == pytest.approx(config.duty_cycle)


def test_config_derivations_preserve_other_fields():
    config = load_nonideal_buck_config()
    assert config.with_dcr(0.0).inductor.dcr_ohm == 0.0
    assert config.with_esr(0.0).capacitor.esr_ohm == 0.0
    assert config.with_variant("C").model_variant == "C"
    assert config.with_duty(0.5).duty_cycle == pytest.approx(0.5)
    assert config.with_transient(end_time_s=2e-3).transient.end_time_s == pytest.approx(2e-3)
    # 不可变对象：原配置不受影响
    assert config.inductor.dcr_ohm == pytest.approx(0.05)


def test_invalid_duty_and_variant_rejected():
    config = load_nonideal_buck_config()
    with pytest.raises(ValueError):
        replace(config, duty_cycle=1.5)
    with pytest.raises(ValueError):
        config.with_variant("Z")
    with pytest.raises(ValueError):
        config.with_dcr(-1.0)


def test_mosfet_level_and_threshold_validation():
    with pytest.raises(ValueError):
        MosfetModelConfig(level=2)
    with pytest.raises(ValueError):
        MosfetModelConfig(threshold_voltage_v=12.0)
    with pytest.raises(ValueError):
        MosfetModelConfig(model_type="PMOS")


def test_gate_driver_must_exceed_threshold():
    mosfet = MosfetModelConfig()
    driver = GateDriverConfig()
    assert driver.validate_for_mosfet(mosfet) == pytest.approx(7.0)
    with pytest.raises(ValueError):
        GateDriverConfig(drive_voltage_v=2.5).validate_for_mosfet(mosfet)
    with pytest.raises(ValueError):
        GateDriverConfig(low_voltage_v=3.5).validate_for_mosfet(mosfet)
    with pytest.raises(ValueError):
        GateDriverConfig(gate_resistance_ohm=0.0)


def test_to_dict_contains_all_sections():
    payload = load_nonideal_buck_config().to_dict()
    for section in (
        "circuit",
        "inductor",
        "capacitor",
        "mosfet",
        "diode",
        "gate_driver",
        "simulation",
        "steady_state",
        "metadata",
    ):
        assert section in payload
    assert payload["metadata"]["data_source"] == "spice_simulation"


def test_device_models_and_temperature_values():
    models = load_device_models()
    for key in (
        "mosfet",
        "diode",
        "mosfet_tests",
        "diode_tests",
        "gate_driver_tests",
        "temperature_tests",
    ):
        assert key in models
    assert models["mosfet"].level == 1
    assert models["diode"].series_resistance_ohm > 0
    assert temperature_values() == (25.0, 50.0, 75.0)


def test_validation_limits_sections():
    limits = load_validation_limits()
    for section in ("integration", "power", "losses", "device"):
        assert section in limits
    assert limits["power"]["efficiency_warning_above_percent"] > 100.0
    assert limits["integration"]["output_voltage_min_v"] < limits["integration"]["output_voltage_max_v"]

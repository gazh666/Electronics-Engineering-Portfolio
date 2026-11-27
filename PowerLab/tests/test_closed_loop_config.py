"""闭环配置测试：默认值、校验、可变副本与 YAML 加载。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from circuits.closed_loop_config import (
    ClosedLoopConfig,
    load_closed_loop_config,
    load_controller_settings,
    load_disturbance_cases,
)
from circuits.dynamic_load import CurrentStepLoad, ResistiveStepLoad
from circuits.input_disturbance import LineStepCase
from control.models import CarrierConfig


def test_default_config_matches_stage7_decisions():
    config = load_closed_loop_config()
    assert config.variant == "E"
    assert config.step_time_s == pytest.approx(25e-9)
    assert config.max_step_time_s <= config.step_time_s
    assert config.open_loop_duty_cycle == pytest.approx(0.4448, abs=1e-3)
    assert config.target_voltage_v == pytest.approx(5.0)
    assert config.carrier.frequency_hz == pytest.approx(config.switching_frequency_hz)
    assert config.soft_start.duration_s == pytest.approx(0.002)


def test_config_validation_rejects_bad_values():
    base = load_closed_loop_config()
    with pytest.raises(ValueError):
        replace(base, variant="Z")
    with pytest.raises(ValueError):
        replace(base, step_time_s=100e-9, max_step_time_s=200e-9)
    with pytest.raises(ValueError):
        replace(base, open_loop_duty_cycle=1.2)
    with pytest.raises(ValueError):
        replace(base, carrier=CarrierConfig(frequency_hz=50e3))
    with pytest.raises(ValueError):
        replace(base, end_time_s=0.0)


def test_timing_mutator_updates_power_stage_transient():
    base = load_closed_loop_config()
    updated = base.with_timing(6e-3, step_time_s=50e-9, max_step_time_s=50e-9)
    assert updated.end_time_s == pytest.approx(6e-3)
    assert updated.power_stage.transient.end_time_s == pytest.approx(6e-3)
    assert updated.transient_config().step_time_s == pytest.approx(50e-9)


def test_named_loads_and_lines_resolve_from_yaml():
    base = load_closed_loop_config()
    current = base.with_named_load("load_step_1a_to_2a")
    assert isinstance(current.load, CurrentStepLoad)
    resistive = base.with_named_load("load_step_resistive_10_to_2p5")
    assert isinstance(resistive.load, ResistiveStepLoad)
    line = base.with_named_line("vin_step_down_12_to_9")
    assert isinstance(line.line, LineStepCase)
    with pytest.raises(KeyError):
        base.with_named_load("unknown_case")


def test_gain_and_windup_mutators_keep_other_fields():
    base = load_closed_loop_config()
    updated = base.with_gains(0.1, 200.0).with_anti_windup("conditional")
    assert updated.controller.kp == pytest.approx(0.1)
    assert updated.controller.ki == pytest.approx(200.0)
    assert updated.controller.anti_windup == "conditional"
    assert updated.power_stage is base.power_stage


def test_overrides_only_allow_known_fields():
    config = load_closed_loop_config(overrides={"variant": "sw", "end_time_s": 6e-3})
    assert config.variant == "SW"
    assert config.end_time_s == pytest.approx(6e-3)
    with pytest.raises(ValueError):
        load_closed_loop_config(overrides={"unknown": 1})


def test_controller_settings_and_disturbance_catalog():
    settings = load_controller_settings()
    assert settings.controller.kp > 0
    assert settings.soft_start.enabled is True
    assert settings.carrier.carrier_type == "sine"
    assert "design" in settings.to_dict()
    cases = load_disturbance_cases()
    assert cases.loads["nominal"] is None
    assert "load_step_1a_to_2a" in cases.loads
    assert "vin_step_down_12_to_9" in cases.lines
    with pytest.raises(KeyError):
        cases.line("unknown")


def test_to_dict_marks_sources_and_variant():
    config = load_closed_loop_config()
    payload = config.to_dict()
    assert payload["metadata"]["data_source"] == "spice_simulation"
    assert payload["metadata"]["closed_loop_variant"] == "E"
    assert payload["variant"] == "E"

"""器件容差与参数白名单测试。"""

from __future__ import annotations

import pytest

from circuits.nonideal_config import load_nonideal_buck_config
from validation.tolerance_analysis import (
    SUPPORTED_PARAMETERS,
    apply_parameter,
    apply_parameters,
    load_component_tolerances,
    one_factor_plan,
    percent_levels,
    tolerance_span_percent,
)


@pytest.fixture(scope="module")
def tolerances():
    payload, values = load_component_tolerances()
    return payload, values


@pytest.fixture(scope="module")
def config():
    return load_nonideal_buck_config()


def test_tolerances_cover_six_whitelisted_parameters(tolerances):
    payload, values = tolerances
    assert len(values) == 6
    assert tuple(values) == SUPPORTED_PARAMETERS
    assert payload["source_type"] == "educational_assumption"
    assert payload["metadata"]["manufacturer_distribution_verified"] is False


def test_tolerance_ranges_bracket_nominal(tolerances):
    _, values = tolerances
    for tolerance in values.values():
        assert tolerance.lower <= tolerance.nominal <= tolerance.upper
        assert tolerance.to_dict()["source_type"] == "educational_assumption"
        assert tolerance.level("low") == tolerance.lower
        assert tolerance.level("nominal") == tolerance.nominal
        assert tolerance.level("high") == tolerance.upper
        with pytest.raises(ValueError):
            tolerance.level("peak")


def test_apply_parameter_updates_inductance(config):
    updated = apply_parameter(config, "inductance_h", 50e-6)
    assert updated.inductor.inductance_h == pytest.approx(50e-6)
    assert config.inductor.inductance_h == pytest.approx(47e-6)


def test_apply_parameter_multiplies_mosfet_kp(config):
    updated = apply_parameter(config, "mosfet_kp_multiplier", 2.0)
    assert updated.mosfet.kp_a_per_v2 == pytest.approx(
        config.mosfet.kp_a_per_v2 * 2.0
    )


def test_apply_parameter_rejects_unknown_parameter(config):
    with pytest.raises(ValueError):
        apply_parameter(config, "switching_frequency_hz", 1e5)


def test_apply_parameter_rejects_nonpositive_value(config):
    with pytest.raises(ValueError):
        apply_parameter(config, "capacitance_f", 0.0)


def test_apply_parameters_applies_several_overrides(config):
    updated = apply_parameters(
        config,
        {"capacitance_f": 120e-6, "capacitor_esr_ohm": 0.039},
    )
    assert updated.capacitor.capacitance_f == pytest.approx(120e-6)
    assert updated.capacitor.esr_ohm == pytest.approx(0.039)


def test_one_factor_plan_is_three_levels_per_parameter(tolerances):
    _, values = tolerances
    plan = one_factor_plan(values)
    assert len(plan) == 18
    first_parameter = sorted(values)[0]
    assert plan[0]["parameter"] == first_parameter
    assert [item["level"] for item in plan[:3]] == ["low", "nominal", "high"]
    expected = [values[first_parameter].level(level) for level in ("low", "nominal", "high")]
    assert [item["value"] for item in plan[:3]] == pytest.approx(expected)
    assert plan[0]["sample_id"] == f"tolerance-{first_parameter}-low"


def test_percent_levels_are_symmetric():
    levels = percent_levels(100.0, 5.0)
    assert levels == {"low": 95.0, "nominal": 100.0, "high": 105.0}
    with pytest.raises(ValueError):
        percent_levels(0.0, 5.0)
    with pytest.raises(ValueError):
        percent_levels(100.0, -1.0)


def test_tolerance_span_percent_matches_definition(tolerances):
    _, values = tolerances
    inductance = values["inductance_h"]
    expected = 100.0 * (inductance.upper - inductance.lower) / (2.0 * inductance.nominal)
    assert tolerance_span_percent(inductance) == pytest.approx(expected)
    assert tolerance_span_percent(inductance) == pytest.approx(20.0)

"""一阶不确定性传播与单因素灵敏度测试。"""

from __future__ import annotations

import math

import pytest

from validation.reference_cases import build_case_config, load_validation_cases
from validation.tolerance_analysis import load_component_tolerances
from validation.uncertainty_analysis import (
    central_sensitivity,
    propagate_first_order,
    sensitivity_from_one_factor,
    uniform_standard_deviation,
)


@pytest.fixture(scope="module")
def tolerances():
    _, mapping = load_component_tolerances()
    return mapping


def test_uniform_standard_deviation_formula(tolerances):
    tolerance = tolerances["inductance_h"]
    expected = (tolerance.upper - tolerance.lower) / math.sqrt(12.0)
    assert uniform_standard_deviation(tolerance) == pytest.approx(expected, rel=1e-12)


def test_central_sensitivity_finite_difference_sign(tolerances):
    config = build_case_config(load_validation_cases()[0])

    def increasing(candidate):
        return {"metric": candidate.inductor.inductance_h ** 2}

    def decreasing(candidate):
        return {"metric": -3.0 * candidate.inductor.inductance_h}

    tolerance = tolerances["inductance_h"]
    positive = central_sensitivity(config, tolerance, metric_function=increasing)
    negative = central_sensitivity(config, tolerance, metric_function=decreasing)
    expected_negative = -3.0
    assert positive["metric"] > 0.0
    assert negative["metric"] < 0.0
    assert negative["metric"] == pytest.approx(expected_negative, rel=1e-4)


def test_central_sensitivity_rejects_non_positive_delta(tolerances):
    config = build_case_config(load_validation_cases()[0])
    with pytest.raises(ValueError):
        central_sensitivity(config, tolerances["inductance_h"], delta_fraction=0.0)


def test_propagate_first_order_combines_in_quadrature(tolerances):
    config = build_case_config(load_validation_cases()[0])
    result = propagate_first_order(config, tolerances, delta_fraction=0.01)
    assert result["method"] == "first_order_independent_propagation"
    assert set(result["sensitivities"]) == set(tolerances)
    for metric, payload in result["metrics"].items():
        expected_sigma = math.sqrt(
            sum(
                (result["sensitivities"][name][metric] * uniform_standard_deviation(tolerance)) ** 2
                for name, tolerance in tolerances.items()
            )
        )
        assert payload["standard_deviation"] == pytest.approx(expected_sigma, rel=1e-9)
        assert payload["variance"] == pytest.approx(expected_sigma ** 2, rel=1e-9)
        assert set(payload["contributions"]) == set(tolerances)
        dominant = max(payload["contributions"], key=lambda name: payload["contributions"][name]["variance"])
        assert payload["dominant_parameter"] == dominant
    assert "not a confidence interval" in result["note"]


def test_sensitivity_from_one_factor_table():
    rows = [
        {
            "sample_id": "tolerance-nominal",
            "level": "nominal",
            "metrics": {"output_voltage_mean_v": 100.0},
        },
        {
            "sample_id": "tolerance-inductance_h-low",
            "parameter": "inductance_h",
            "level": "low",
            "value": 9.0,
            "nominal_value": 10.0,
            "metrics": {"output_voltage_mean_v": 90.0},
        },
        {
            "sample_id": "tolerance-inductance_h-high",
            "parameter": "inductance_h",
            "level": "high",
            "value": 11.0,
            "nominal_value": 10.0,
            "metrics": {"output_voltage_mean_v": 110.0},
        },
    ]
    payload = sensitivity_from_one_factor(rows)
    assert payload["status"] == "OK"
    assert payload["nominal"] == pytest.approx(100.0)
    assert payload["ranking"] == ["inductance_h"]
    entry = payload["parameters"]["inductance_h"]
    assert entry["mean_sensitivity"] == pytest.approx(10.0)
    assert len(entry["sensitivities"]) == 2


def test_sensitivity_from_one_factor_missing_nominal_is_insufficient():
    payload = sensitivity_from_one_factor(
        [{"sample_id": "tolerance-other", "parameter": "inductance_h", "level": "low"}]
    )
    assert payload["status"] == "INSUFFICIENT_DATA"

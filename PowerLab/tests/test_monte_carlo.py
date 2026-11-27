"""Monte Carlo 采样与样本持久化测试。"""

from __future__ import annotations

import pytest

from validation.monte_carlo import (
    MonteCarloSample,
    cache_signature,
    generate_samples,
    load_samples_csv,
    sample_key,
    sampling_provenance,
    validate_sample_values,
    write_samples_csv,
)
from validation.reference_cases import build_case_config, load_validation_cases
from validation.tolerance_analysis import apply_parameter, load_component_tolerances


@pytest.fixture(scope="module")
def tolerances():
    _, mapping = load_component_tolerances()
    return mapping


def test_generate_samples_is_reproducible_for_same_seed(tolerances):
    first = generate_samples(tolerances, 8, seed=7)
    second = generate_samples(tolerances, 8, seed=7)
    assert [sample.sample_id for sample in first] == [f"mc-{i:03d}" for i in range(1, 9)]
    assert [sample.values for sample in first] == [sample.values for sample in second]


def test_generate_samples_differs_for_another_seed(tolerances):
    first = generate_samples(tolerances, 8, seed=7)
    other = generate_samples(tolerances, 8, seed=8)
    assert any(
        a.values != b.values for a, b in zip(first, other)
    )


def test_sample_values_stay_inside_declared_ranges(tolerances):
    for sample in generate_samples(tolerances, 40, seed=11):
        assert set(sample.values) == set(tolerances)
        for name, value in sample.values.items():
            assert tolerances[name].lower <= value <= tolerances[name].upper


def test_validate_sample_values_flags_out_of_range_and_missing(tolerances):
    values = {name: tolerance.nominal for name, tolerance in tolerances.items()}
    values["inductance_h"] = tolerances["inductance_h"].upper * 2.0
    del values["capacitance_f"]
    problems = validate_sample_values(
        MonteCarloSample(sample_id="bad", values=values), tolerances
    )
    assert len(problems) == 2
    assert any("outside" in item for item in problems)
    assert any("missing" in item for item in problems)


def test_samples_csv_round_trip(tolerances, tmp_path):
    samples = generate_samples(tolerances, 5, seed=3)
    samples[1].status = "ERROR"
    samples[1].failure_reason = "synthetic failure"
    path = write_samples_csv(tmp_path / "samples.csv", samples)
    assert path.exists()
    loaded = load_samples_csv(path)
    assert [item.sample_id for item in loaded] == [item.sample_id for item in samples]
    assert loaded[1].status == "ERROR"
    assert loaded[1].failure_reason == "synthetic failure"
    for original, restored in zip(samples, loaded):
        for name, value in original.values.items():
            assert restored.values[name] == pytest.approx(value)


def test_sample_key_changes_with_parameter_value(tolerances):
    base = {name: tolerance.nominal for name, tolerance in tolerances.items()}
    changed = dict(base)
    changed["capacitance_f"] = base["capacitance_f"] * 1.01
    assert sample_key(base) == sample_key(dict(base))
    assert sample_key(base) != sample_key(changed)


def test_cache_signature_changes_with_parameter_value():
    config = build_case_config(load_validation_cases()[0])
    changed = apply_parameter(config, "inductance_h", config.inductor.inductance_h * 1.02)
    baseline = cache_signature(config, "E", 50e-9)
    assert baseline == cache_signature(config, "E", 50e-9)
    assert cache_signature(changed, "E", 50e-9) != baseline
    assert "variant=E" in baseline


def test_sampling_provenance_states_educational_assumption(tolerances):
    provenance = sampling_provenance(tolerances, 12, seed=7, profile="smoke")
    assert provenance["random_seed"] == 7
    assert provenance["profile"] == "smoke"
    assert provenance["sample_count"] == 12
    assert provenance["distribution_source"] == "educational_assumption"
    assert provenance["manufacturer_distribution_verified"] is False
    assert set(provenance["parameters"]) == set(tolerances)
    assert "not a vendor lot distribution" in provenance["note"]

"""第五阶段阈值配置：可追溯性、边界与非法配置拒绝。"""

from __future__ import annotations

import copy

import pytest

from protection.limits import (
    ProtectionConfigError,
    build_limits,
    load_protection_config,
)


@pytest.fixture()
def config() -> dict:
    return copy.deepcopy(load_protection_config())


def test_thresholds_inside_measurement_domain():
    limits = build_limits()
    assert limits.cell_overvoltage_trip_v <= limits.afe_measurement_max_v
    assert limits.cell_overvoltage_trip_v >= limits.model_terminal_reference_max_v
    assert limits.cell_undervoltage_trip_v >= limits.afe_measurement_min_v
    assert limits.cell_undervoltage_trip_v <= limits.model_terminal_reference_min_v
    assert limits.cell_overvoltage_release_v < limits.cell_overvoltage_trip_v
    assert limits.cell_undervoltage_release_v > limits.cell_undervoltage_trip_v


def test_hysteresis_widths_are_positive():
    limits = build_limits()
    assert limits.cell_overvoltage_trip_v - limits.cell_overvoltage_release_v == pytest.approx(0.10)
    assert limits.cell_undervoltage_release_v - limits.cell_undervoltage_trip_v == pytest.approx(0.20)


def test_current_and_temperature_ordering():
    limits = build_limits()
    assert limits.charge_overcurrent_release_a < limits.charge_overcurrent_trip_a
    assert limits.discharge_overcurrent_release_a < limits.discharge_overcurrent_trip_a
    assert limits.short_circuit_trip_a > limits.discharge_overcurrent_trip_a
    assert limits.over_temperature_release_c < limits.over_temperature_trip_c
    assert limits.over_temperature_trip_c > limits.charge_temperature_max_c


def test_provenance_reports_bounds():
    provenance = build_limits().threshold_provenance()
    assert provenance["cell_overvoltage_trip_v"]["upper_bound"] == pytest.approx(4.25)
    assert provenance["cell_overvoltage_trip_v"]["lower_bound"] == pytest.approx(4.2)
    assert provenance["cell_undervoltage_trip_v"]["lower_bound"] == pytest.approx(2.5)


def test_rejects_overvoltage_above_measurement_range(config):
    config["limits"]["cell_overvoltage_trip_v"] = 4.30
    with pytest.raises(ProtectionConfigError):
        build_limits(config)


def test_rejects_overvoltage_below_model_reference(config):
    config["limits"]["cell_overvoltage_trip_v"] = 4.10
    with pytest.raises(ProtectionConfigError):
        build_limits(config)


def test_rejects_undervoltage_below_measurement_range(config):
    config["limits"]["cell_undervoltage_trip_v"] = 2.40
    with pytest.raises(ProtectionConfigError):
        build_limits(config)


def test_rejects_release_order_inversion(config):
    config["limits"]["cell_overvoltage_release_v"] = 4.30
    with pytest.raises(ProtectionConfigError):
        build_limits(config)


def test_rejects_short_circuit_below_discharge_limit(config):
    config["limits"]["short_circuit_trip_a"] = 3.0
    with pytest.raises(ProtectionConfigError):
        build_limits(config)


def test_rejects_automatic_restart(config):
    config["recovery"]["automatic_restart"] = True
    with pytest.raises(ProtectionConfigError):
        build_limits(config)


def test_rejects_balance_start_above_overvoltage(config):
    config["balancing"]["start_cell_voltage_v"] = 4.3
    with pytest.raises(ProtectionConfigError):
        build_limits(config)


def test_rejects_negative_delay(config):
    config["timing"]["overvoltage_delay_s"] = 0.0
    with pytest.raises(ProtectionConfigError):
        build_limits(config)

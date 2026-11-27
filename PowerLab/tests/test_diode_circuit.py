"""二极管直流伏安特性：真实 ngspice 扫描与 Shockley 理论边界。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.error_metrics import calculate_error_metrics
from analysis.theory import DATA_SOURCE, diode_ideal_current, diode_thermal_voltage
from circuits.diode_circuit import DIODE_MODEL_NAME, build_diode_iv_circuit
from circuits.models import DiodeParameters
from simulations.runner import SimulationRunner


@pytest.fixture(scope="module")
def scan_data():
    parameters = DiodeParameters()
    circuit = build_diode_iv_circuit(parameters)
    result = SimulationRunner(25.0).run_dc(circuit, "bias", -1.0, 0.8, 0.01)
    voltage = result.data["sweep_v"].to_numpy()
    current = -result.data["vbias_branch_current_a"].to_numpy()
    return voltage, current, result


def test_scan_points_and_voltage_axis(scan_data):
    voltage, current, result = scan_data
    assert result.point_count == 181
    assert voltage[0] == pytest.approx(-1.0)
    assert voltage[-1] == pytest.approx(0.8)
    assert current.shape == voltage.shape


def test_reverse_current_is_nanoamp(scan_data):
    voltage, current, _ = scan_data
    reverse = float(np.interp(-1.0, voltage, current))
    assert reverse == pytest.approx(-1e-9, abs=1e-10)


def test_forward_current_monotonic_and_large(scan_data):
    voltage, current, _ = scan_data
    forward_mask = voltage > 0.5
    assert np.all(np.diff(current[forward_mask]) > 0)
    at_0p8 = float(np.interp(0.8, voltage, current))
    assert at_0p8 > 0.02


def test_turn_on_voltage_reasonable(scan_data):
    voltage, current, _ = scan_data
    for target in (1e-3, 1e-2):
        crossing = float(np.interp(target, current, voltage))
        assert 0.5 < crossing < 0.85


def test_shockley_upper_bound_with_series_resistance(scan_data):
    voltage, current, _ = scan_data
    ideal = diode_ideal_current(voltage, 1e-9, 1.8, 25.0)
    forward = voltage > 0.5
    assert np.all(ideal[forward] > current[forward])

    metrics = calculate_error_metrics(current, ideal)
    assert metrics["max_absolute_error"] > 0.0
    assert np.isfinite(metrics["rmse"])


def test_thermal_voltage_and_model_name():
    assert diode_thermal_voltage(25.0) == pytest.approx(0.0256926, rel=1e-5)
    assert DIODE_MODEL_NAME == "DTEST"
    assert DATA_SOURCE == "analytical_theory"


def test_invalid_diode_parameters_raise():
    with pytest.raises(ValueError):
        DiodeParameters(saturation_current_a=0.0)
    with pytest.raises(ValueError):
        DiodeParameters(ideality_factor=0.0)

"""PyBaMM 封装测试（含真实求解）。"""

from __future__ import annotations

import numpy as np
import pytest

from battery_models.pybamm_backend import (
    BatteryModelError,
    BatterySimulationConfig,
    PyBaMMBackend,
)


def test_create_model_names():
    backend = PyBaMMBackend("SPM")
    assert backend.create_model("SPM").name
    assert backend.create_model("Thevenin").name
    with pytest.raises(BatteryModelError):
        backend.create_model("DFN_NOT_SUPPORTED")


def test_invalid_config_rejected():
    config = BatterySimulationConfig(model_name="SPM", duration_s=-1)
    with pytest.raises(BatteryModelError):
        config.validate()
    config = BatterySimulationConfig(model_name="SPM", duration_s=10, initial_soc=1.5)
    with pytest.raises(BatteryModelError):
        config.validate()


def test_unknown_parameter_set_rejected():
    backend = PyBaMMBackend("SPM")
    config = BatterySimulationConfig(model_name="SPM", duration_s=10, parameter_set="NotARealSet")
    with pytest.raises(BatteryModelError):
        backend.run(config)


def test_spm_real_run_waveform():
    backend = PyBaMMBackend("SPM")
    config = BatterySimulationConfig(model_name="SPM", duration_s=120, output_points=30)
    result = backend.run(config)
    frame = result["waveform"]
    assert len(frame) >= 2
    assert set(["time_s", "voltage_v", "current_a"]).issubset(frame.columns)
    for column in ("time_s", "voltage_v", "current_a"):
        assert np.isfinite(frame[column].to_numpy(dtype=float)).all()
    assert result["metadata"]["solver"]
    assert result["metadata"]["termination"]
    assert result["metadata"]["data_source"] == "pybamm_simulation"
    assert np.all(np.diff(frame["time_s"].to_numpy(dtype=float)) > 0)


def test_thevenin_initial_soc_applied():
    backend = PyBaMMBackend("Thevenin")
    config = BatterySimulationConfig(model_name="Thevenin", duration_s=60, initial_soc=0.8, output_points=20)
    result = backend.run(config)
    frame = result["waveform"]
    assert abs(float(frame["soc"].iloc[0]) - 0.8) < 0.02


def test_extract_waveform_rejects_bad_solution():
    class FakeSolution(dict):
        def __getitem__(self, key):
            class Entry:
                def __init__(self, values):
                    self.entries = values

            mapping = {"Time [s]": [0, 1], "Voltage [V]": [4.0], "Current [A]": [-1.0, -1.0]}
            return Entry(mapping[key])

    from battery_models.pybamm_backend import SimulationRunError

    with pytest.raises(SimulationRunError):
        PyBaMMBackend("SPM").extract_waveform(FakeSolution())

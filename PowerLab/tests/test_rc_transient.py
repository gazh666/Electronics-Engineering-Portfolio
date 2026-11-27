"""RC 瞬态：真实波形、时间序列质量与检查点误差。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.metrics import rc_metrics
from circuits.rc import build_rc_charging
from scripts.rc_transient_demo import simulate_rc_transient


@pytest.fixture(scope="module")
def frame():
    return simulate_rc_transient()


@pytest.fixture(scope="module")
def frame_metrics(frame):
    return rc_metrics(
        frame["time_s"].to_numpy(),
        frame["spice_vout_v"].to_numpy(),
        vin_v=5.0,
        tau_s=1e-3,
        checkpoints_tau=(1, 2, 3, 5),
    )


def test_transient_has_enough_samples(frame):
    assert len(frame) > 10


def test_transient_values_are_finite(frame):
    assert np.isfinite(frame["time_s"].to_numpy()).all()
    assert np.isfinite(frame["spice_vout_v"].to_numpy()).all()


def test_time_is_strictly_increasing(frame):
    assert np.all(np.diff(frame["time_s"].to_numpy()) > 0)


def test_voltage_at_one_tau(frame):
    time_s = frame["time_s"].to_numpy()
    voltage = frame["spice_vout_v"].to_numpy()
    voltage_at_tau = np.interp(1e-3, time_s, voltage)
    assert voltage_at_tau == pytest.approx(3.1606, abs=0.03)


def test_final_voltage_approaches_input(frame):
    assert frame["spice_vout_v"].iloc[-1] == pytest.approx(5.0, abs=0.03)


def test_metrics_cover_all_checkpoints(frame_metrics):
    assert frame_metrics["sample_count"] > 10
    assert len(frame_metrics["checkpoints"]) == 4
    assert frame_metrics["rmse_v"] >= 0
    assert np.isfinite(frame_metrics["rmse_v"])


def test_invalid_rc_parameters_raise():
    with pytest.raises(ValueError):
        build_rc_charging(resistance_ohm=0.0)
    with pytest.raises(ValueError):
        build_rc_charging(capacitance_f=float("nan"))


def test_invalid_time_series_rejected():
    with pytest.raises(ValueError):
        rc_metrics([0.0, 0.0, 1e-3], [0.0, 1.0, 2.0], vin_v=5.0, tau_s=1e-3)
    with pytest.raises(ValueError):
        rc_metrics([0.0, 1e-3], [0.0, float("nan")], vin_v=5.0, tau_s=1e-3)

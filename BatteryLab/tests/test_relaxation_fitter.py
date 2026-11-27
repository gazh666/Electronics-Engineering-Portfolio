"""静置恢复指数拟合与 RC 反推。"""

from __future__ import annotations

import numpy as np
import pytest

from identification.models import IdentificationError
from identification.relaxation_fitter import fit_relaxation


def _synthetic(order=1, tau1=120.0, tau2=1200.0, a1=0.08, a2=0.04, v_inf=3.82, duration=7200.0, dt=10.0):
    time = np.arange(0.0, duration + dt, dt)
    voltage = np.full(time.size, v_inf) - a1 * np.exp(-time / tau1)
    if order == 2:
        voltage -= a2 * np.exp(-time / tau2)
    return time, voltage


def test_single_exponential_recovers_tau():
    time, voltage = _synthetic(order=1)
    fit = fit_relaxation(time, voltage, order=1, tau1_bounds_s=(5.0, 300.0))
    assert fit.fitting_success
    assert fit.time_constants_s[0] == pytest.approx(120.0, rel=0.05)
    assert fit.rmse_v < 1e-6
    assert fit.status == "IDENTIFIED"


def test_double_exponential_recovers_two_taus():
    time, voltage = _synthetic(order=2)
    fit = fit_relaxation(time, voltage, order=2, tau1_bounds_s=(5.0, 300.0), tau2_bounds_s=(300.0, 5000.0))
    taus = fit.time_constants_s
    assert taus[0] < taus[1]
    assert fit.rmse_v < 1e-5
    assert abs(taus[1] - 1200.0) / 1200.0 < 0.15


def test_derive_rc_from_pulse():
    time, voltage = _synthetic(order=1, a1=0.06, tau1=100.0)
    fit = fit_relaxation(time, voltage, order=1, tau1_bounds_s=(5.0, 300.0))
    resistance, capacitance = fit.derive_rc(2.0, 600.0, 0)
    assert resistance > 0 and capacitance > 0
    assert resistance == pytest.approx(0.06 / (2.0 * (1 - np.exp(-6.0))), rel=0.05)


def test_insufficient_rest_rejected():
    time, voltage = _synthetic(order=2, duration=200.0)
    with pytest.raises(IdentificationError):
        fit_relaxation(time, voltage, order=2, tau2_bounds_s=(100.0, 5000.0))


def test_non_monotonic_time_rejected():
    time, voltage = _synthetic(order=1, duration=1000.0)
    time[5] = time[4]
    with pytest.raises(IdentificationError):
        fit_relaxation(time, voltage, order=1)

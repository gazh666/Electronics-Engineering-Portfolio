"""第六阶段 CC→CV 切换识别与分阶段电量。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.cc_cv_transition import (
    classify_charge_regions,
    detect_cc_to_cv_transition,
    phase_charge_totals_ah,
)


def _profile():
    time = np.arange(0.0, 1.0, 1e-3)
    voltage = np.where(time < 0.5, 11.5, np.minimum(12.15, 11.5 + (time - 0.5) * 2.0))
    current = np.where(time < 0.5, 1.0, np.maximum(0.1, 1.0 - (time - 0.5) * 4.0))
    return time, voltage, current


def test_detects_transition_after_holding_tolerance():
    time, voltage, _ = _profile()
    transition = detect_cc_to_cv_transition(time, voltage, 12.15, 0.02, hold_time_s=5e-3)
    assert transition is not None
    assert 0.80 <= transition <= 0.84


def test_no_transition_when_never_reaches_target():
    time = np.arange(0.0, 0.1, 1e-3)
    voltage = np.full(time.shape, 11.5)
    assert detect_cc_to_cv_transition(time, voltage, 12.15, 0.02, hold_time_s=5e-3) is None


def test_phase_charge_totals_sum_to_total():
    time, voltage, current = _profile()
    totals = phase_charge_totals_ah(time, voltage, current, 12.15, 0.02)
    assert totals["cc_charge_ah"] > 0.0
    assert totals["cv_charge_ah"] > 0.0
    assert totals["total_charge_ah"] == pytest.approx(
        totals["cc_charge_ah"] + totals["cv_charge_ah"], rel=1e-9
    )


def test_region_classification_labels():
    time, voltage, _ = _profile()
    labels = classify_charge_regions(time, voltage, 12.15, 0.02)
    assert set(np.unique(labels)) == {"CC", "CV"}
    assert labels[0] == "CC"
    assert labels[-1] == "CV"

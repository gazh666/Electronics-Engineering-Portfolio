"""环路分析测试：穿越、裕度、极点分类与带宽。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from control.loop_analysis import (
    analyze_loop,
    bandwidth_hz,
    classify_poles,
    closed_loop_characteristic,
    closed_loop_poles,
    closed_loop_transfer,
    loop_gain,
    pi_response,
    summarize_loop,
)
from control.transfer_functions import TransferFunction, frequency_grid


def test_pi_response_magnitude_at_low_frequency():
    frequency_hz = 0.1
    response = pi_response(1.0, 100.0, np.array([frequency_hz]))
    expected = math.hypot(1.0, 100.0 / (2.0 * math.pi * frequency_hz))
    assert abs(response[0]) > 1e2
    assert abs(response[0]) == pytest.approx(expected)
    with pytest.raises(ValueError):
        pi_response(-1.0, 1.0, np.array([1.0]))


def test_loop_gain_is_product_of_pi_and_plant():
    plant = TransferFunction([1.0], [1.0, 1.0])
    frequencies = np.array([1.0, 10.0])
    response = loop_gain(frequencies, plant, 1.0, 1.0)
    expected = (1.0 + 1.0 / (1j * 2 * math.pi * frequencies)) * (
        1.0 / (1j * 2 * math.pi * frequencies + 1.0)
    )
    assert np.allclose(response, expected)


def test_integrator_loop_has_ninety_degree_margin():
    plant = TransferFunction([1.0], [1.0, 1.0])
    frequencies = np.logspace(-2, 3, 600)
    response = loop_gain(frequencies, plant, 1.0, 1.0)
    summary = analyze_loop(frequencies, response)
    assert summary["status"] == "STABLE"
    assert summary["phase_margin_deg"] == pytest.approx(90.0, abs=1.0)
    assert len(summary["magnitude_crossings"]) == 1
    assert summary["analysis_type"] == "linearized_average_model"


def test_no_crossover_does_not_fake_margin():
    frequencies = np.logspace(0, 4, 100)
    summary = analyze_loop(frequencies, np.full(frequencies.size, 0.5 + 0.0j))
    assert summary["status"] == "NO_CROSSOVER"
    assert math.isnan(summary["phase_margin_deg"])
    assert math.isnan(summary["gain_margin_db"])
    assert summary["messages"]


def test_analyze_loop_validates_shapes():
    with pytest.raises(ValueError):
        analyze_loop([1.0, 2.0], np.array([1.0 + 0j, 1.0 + 0j]))
    with pytest.raises(ValueError):
        analyze_loop([1.0, 2.0, 3.0], np.array([1.0 + 0j]))


def test_closed_loop_poles_for_integrator_loop():
    plant = TransferFunction([1.0], [1.0, 1.0])
    characteristic = closed_loop_characteristic(plant, 1.0, 1.0)
    assert np.allclose(characteristic, [1.0, 2.0, 1.0])
    poles = closed_loop_poles(plant, 1.0, 1.0)
    assert np.allclose(np.sort(np.real(poles)), [-1.0, -1.0])
    summary = classify_poles(poles)
    assert summary["status"] == "STABLE"
    assert summary["minimum_decay_rate"] == pytest.approx(1.0)


def test_classify_poles_states():
    unstable = classify_poles(np.array([1.0 + 0.0j, -2.0 + 0.0j]))
    assert unstable["status"] == "UNSTABLE"
    marginal = classify_poles(np.array([0.0 + 1.0j, 0.0 - 1.0j]))
    assert marginal["status"] == "MARGINAL"
    empty = classify_poles(np.array([]))
    assert empty["status"] == "NOT_RESOLVED"


def test_closed_loop_transfer_and_bandwidth():
    plant = TransferFunction([1.0], [1.0, 1.0])
    closed = closed_loop_transfer(plant, 1.0, 1.0)
    assert closed.dc_gain == pytest.approx(1.0)
    bandwidth = bandwidth_hz(plant, 1.0, 1.0, start_hz=0.01)
    assert bandwidth == pytest.approx(1.0 / (2 * math.pi), rel=0.05)


def test_summarize_loop_combines_outputs():
    plant = TransferFunction([1.0], [1.0, 1.0])
    summary = summarize_loop(frequency_grid(0.01, 1e6), plant, 1.0, 1.0)
    assert summary["status"] in ("STABLE", "LOW_MARGIN")
    assert "closed_loop_poles" in summary
    assert summary["bandwidth_hz"] > 0

"""传递函数工具测试。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from control.transfer_functions import (
    TransferFunction,
    cascade,
    damping_ratio,
    esr_zero_hz,
    evaluate_many,
    frequency_grid,
    ideal_buck_control_to_output,
    is_stable_transfer,
    natural_frequency_hz,
    nonideal_buck_control_to_output,
    quality_factor,
)
from control.averaged_buck import AveragedBuckParameters


def test_transfer_function_evaluation_and_dc_gain():
    transfer = TransferFunction([2.0], [1.0, 2.0, 1.0])
    assert transfer.dc_gain == pytest.approx(2.0)
    assert transfer.evaluate(0.0) == pytest.approx(2.0)
    poles = transfer.poles
    assert np.allclose(np.sort_complex(poles), np.array([-1.0, -1.0]))
    assert transfer.zeros.size == 0


def test_invalid_denominator_rejected():
    with pytest.raises(ValueError):
        TransferFunction([1.0], [0.0, 0.0])


def test_ideal_buck_dc_gain_and_poles():
    transfer = ideal_buck_control_to_output(12.0, 47e-6, 100e-6, 2.5)
    assert transfer.dc_gain == pytest.approx(12.0)
    assert transfer.poles.size == 2
    assert np.all(np.real(transfer.poles) < 0)


def test_natural_frequency_and_damping():
    expected_frequency = 1.0 / (2 * math.pi * math.sqrt(47e-6 * 100e-6))
    assert natural_frequency_hz(47e-6, 100e-6) == pytest.approx(expected_frequency)
    zeta = damping_ratio(47e-6, 100e-6, 2.5)
    assert zeta == pytest.approx(0.5 / 2.5 * math.sqrt(47e-6 / 100e-6))
    assert quality_factor(47e-6, 100e-6, 2.5) == pytest.approx(1.0 / (2 * zeta))


def test_esr_zero_frequency():
    assert esr_zero_hz(100e-6, 0.03) == pytest.approx(1.0 / (2 * math.pi * 0.03 * 100e-6))


def test_frequency_grid_spans_requested_range():
    grid = frequency_grid(1.0, 1e6, 60)
    assert grid[0] == pytest.approx(1.0)
    assert grid[-1] == pytest.approx(1e6)
    assert len(grid) >= 300
    with pytest.raises(ValueError):
        frequency_grid(10.0, 1.0)


def test_cascade_multiplies_polynomials():
    first = TransferFunction([1.0], [1.0, 1.0])
    second = TransferFunction([2.0], [1.0, 2.0])
    combined = cascade(first, second)
    assert np.allclose(combined.num, [2.0])
    assert np.allclose(combined.den, [1.0, 3.0, 2.0])


def test_evaluate_many_shapes_and_stability():
    transfer = ideal_buck_control_to_output(12.0, 47e-6, 100e-6, 2.5)
    magnitude, phase = evaluate_many(transfer, [1.0, 100.0, 1e4])
    assert magnitude.shape == (3,)
    assert phase.shape == (3,)
    assert magnitude[0] > magnitude[-1]
    assert is_stable_transfer(transfer) is True
    assert is_stable_transfer(TransferFunction([1.0], [1.0, -1.0])) is False


def test_nonideal_transfer_has_numeric_linearization_metadata():
    transfer, metadata = nonideal_buck_control_to_output(AveragedBuckParameters(), 0.44)
    assert transfer.den.size >= 2
    assert metadata["model_source"] == "averaged_model"
    assert metadata["method"] == "numeric_jacobian"
    assert metadata["linearization_point"]["duty"] == pytest.approx(0.44)

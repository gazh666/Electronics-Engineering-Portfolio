"""保护比较器：迟滞、确认延时、传输延时与抖动抑制。"""

from __future__ import annotations

import numpy as np
import pytest

from protection.comparator import (
    ComparatorConfig,
    ComparatorError,
    HysteresisComparator,
    chatter_count,
    evaluate_comparator,
    first_trip_time,
)


def test_trip_requires_confirmation_delay():
    config = ComparatorConfig(
        name="OV", threshold=4.25, hysteresis=0.1, confirmation_delay_s=0.05, direction="high"
    )
    comparator = HysteresisComparator(config)
    assert comparator.step(4.30, 0.0).output is False
    assert comparator.step(4.30, 0.049).output is False
    reading = comparator.step(4.30, 0.050)
    assert reading.tripped is True
    assert reading.output is True
    assert reading.trip_time_s == pytest.approx(0.050)


def test_release_uses_hysteresis_and_delay():
    config = ComparatorConfig(
        name="OV", threshold=4.25, hysteresis=0.1, confirmation_delay_s=0.05, direction="high"
    )
    comparator = HysteresisComparator(config)
    comparator.step(4.30, 0.0)
    comparator.step(4.30, 0.05)
    # 4.20 高于释放点 4.15，仍保持锁存。
    assert comparator.step(4.20, 0.10).output is True
    assert comparator.step(4.10, 0.20).output is True  # 确认延时未到
    assert comparator.step(4.10, 0.25).output is False


def test_propagation_delay_shifts_output():
    config = ComparatorConfig(
        name="OV",
        threshold=4.25,
        hysteresis=0.1,
        confirmation_delay_s=0.0,
        propagation_delay_s=0.002,
        direction="high",
    )
    comparator = HysteresisComparator(config)
    assert comparator.step(4.30, 0.0).output is False
    assert comparator.step(4.30, 0.001).output is False
    assert comparator.step(4.30, 0.002).output is True


def test_undervoltage_direction():
    config = ComparatorConfig(
        name="UV", threshold=2.80, hysteresis=0.2, confirmation_delay_s=0.0, direction="low"
    )
    comparator = HysteresisComparator(config)
    assert comparator.step(3.0, 0.0).output is False
    assert comparator.step(2.75, 0.001).output is True
    assert comparator.step(2.95, 0.002).output is True  # 未超过释放点 3.0
    assert comparator.step(3.01, 0.003).output is False


def test_hysteresis_suppresses_noise_chatter():
    rng = np.random.default_rng(7)
    times = np.arange(0.0, 2.0, 0.001)
    values = 4.25 + rng.normal(0.0, 0.002, times.size)
    with_hysteresis = ComparatorConfig(
        name="H", threshold=4.25, hysteresis=0.1, confirmation_delay_s=0.0, direction="high"
    )
    no_hysteresis = ComparatorConfig(
        name="N", threshold=4.25, hysteresis=0.0, confirmation_delay_s=0.0, direction="high"
    )
    quiet = evaluate_comparator(with_hysteresis, values.tolist(), times.tolist())
    noisy = evaluate_comparator(no_hysteresis, values.tolist(), times.tolist())
    assert chatter_count(quiet) <= 2
    assert chatter_count(noisy) > 100


def test_rejects_time_going_backwards():
    comparator = HysteresisComparator(
        ComparatorConfig(name="X", threshold=1.0, hysteresis=0.1, confirmation_delay_s=0.0)
    )
    comparator.step(0.9, 1.0)
    with pytest.raises(ComparatorError):
        comparator.step(0.9, 0.5)


def test_rejects_non_finite_input():
    comparator = HysteresisComparator(
        ComparatorConfig(name="X", threshold=1.0, hysteresis=0.1, confirmation_delay_s=0.0)
    )
    with pytest.raises(ComparatorError):
        comparator.step(float("nan"), 0.0)


def test_first_trip_time():
    config = ComparatorConfig(
        name="OV", threshold=4.25, hysteresis=0.1, confirmation_delay_s=0.01, direction="high"
    )
    readings = evaluate_comparator(config, [4.0, 4.3, 4.3, 4.3], [0.0, 0.005, 0.015, 0.025])
    assert first_trip_time(readings) == pytest.approx(0.015)

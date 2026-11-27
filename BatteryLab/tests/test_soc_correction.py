"""静置 OCV 校正单元测试。"""

from __future__ import annotations

import math

import pytest

from estimation.soc_correction import (
    CorrectionError,
    SOCCorrectionScheduler,
    correct_soc_from_ocv,
)


def test_weighted_correction():
    result = correct_soc_from_ocv(0.50, 0.60, eligible=True, weight=0.2)
    assert result.applied is True
    assert math.isclose(result.correction, 0.02, abs_tol=1e-12)
    assert math.isclose(result.soc, 0.52, abs_tol=1e-12)


def test_correction_is_limited():
    result = correct_soc_from_ocv(0.50, 0.90, eligible=True, weight=0.5, maximum_correction=0.02)
    assert math.isclose(result.correction, 0.02, abs_tol=1e-12)
    assert math.isclose(result.soc, 0.52, abs_tol=1e-12)


def test_ineligible_returns_unchanged():
    result = correct_soc_from_ocv(0.50, None, eligible=False)
    assert result.applied is False
    assert result.soc == 0.50
    assert result.reason == "CORRECTION_NOT_ELIGIBLE"


def test_scheduler_respects_interval():
    scheduler = SOCCorrectionScheduler(interval_s=60.0, weight=0.2, maximum_correction=0.02)
    first = scheduler.apply(0.0, 0.50, 0.60, True)
    second = scheduler.apply(30.0, 0.50, 0.60, True)
    third = scheduler.apply(60.0, 0.50, 0.60, True)
    assert first is not None and first.applied
    assert second is None
    assert third is not None and third.applied
    assert scheduler.correction_count == 2
    assert len(scheduler.events) == 2


def test_invalid_inputs_raise():
    with pytest.raises(CorrectionError):
        correct_soc_from_ocv(float("nan"), 0.5, True)
    with pytest.raises(CorrectionError):
        correct_soc_from_ocv(0.5, 0.5, True, weight=1.5)
    with pytest.raises(CorrectionError):
        SOCCorrectionScheduler(interval_s=0.0)

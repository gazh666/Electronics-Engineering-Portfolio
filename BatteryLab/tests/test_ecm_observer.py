"""ECM 状态观测器单元测试。"""

from __future__ import annotations

import math

import pytest

from estimation.coulomb_counter import CoulombCounter
from estimation.ecm_observer import ECMObserver, ObserverError, ObserverRCBranch


class LinearOCV:
    """测试用线性 OCV：V = 3.0 + 1.0 * SOC。"""

    def voltage_at(self, soc: float) -> float:
        return 3.0 + float(soc)

    def slope_at(self, soc: float) -> float:
        return 1.0


class FlatOCV(LinearOCV):
    def slope_at(self, soc: float) -> float:
        return 0.1


def _observer(**kwargs) -> ECMObserver:
    values = dict(
        counter=CoulombCounter(capacity_ah=2.0, soc=0.5),
        r0_ohm=0.05,
        branches=(ObserverRCBranch(resistance_ohm=0.02, time_constant_s=10.0),),
        ocv_model=LinearOCV(),
        correction_time_constant_s=120.0,
        minimum_ocv_slope=0.2,
        maximum_correction_rate=0.001,
        maximum_residual_v=0.35,
        current_step_threshold_a=0.5,
    )
    values.update(kwargs)
    return ECMObserver(**values)


def test_rc_exact_discretization():
    observer = _observer()
    observer.update_rc(1.0, 10.0)
    expected = 0.02 * 1.0 * (1.0 - math.exp(-1.0))
    assert math.isclose(observer.polarization[0], expected, rel_tol=1e-12)


def test_predicted_voltage_formula():
    observer = _observer()
    polarization = 0.02 * 1.0 * (1.0 - math.exp(-1.0 / 10.0))
    soc_after = 0.5 - 1.0 / (3600.0 * 2.0)
    predicted = 3.0 + soc_after - 1.0 * 0.05 - polarization
    result = observer.step(1.0, 1.0, predicted, 1.0)
    assert math.isclose(result.predicted_voltage_v, predicted, abs_tol=1e-12)
    assert math.isclose(result.residual_v, 0.0, abs_tol=1e-12)
    assert result.status == "VOLTAGE_CORRECTED"


def test_residual_gate_blocks_correction():
    observer = _observer()
    result = observer.step(0.0, 0.0, 4.0, 1.0)
    assert result.status == "RESIDUAL_GATED"
    assert result.correction == 0.0


def test_low_ocv_slope_blocks_correction():
    observer = _observer(ocv_model=FlatOCV())
    result = observer.step(0.0, 0.0, 3.51, 1.0)
    assert result.status == "LOW_OBSERVABILITY"
    assert result.correction == 0.0


def test_correction_rate_is_limited():
    observer = _observer()
    predicted = 3.5
    result = observer.step(0.0, 0.0, predicted + 0.30, 1.0)
    assert result.status == "VOLTAGE_CORRECTED"
    assert math.isclose(result.correction, 0.001, abs_tol=1e-12)


def test_current_step_holds_correction():
    observed = _observer()
    predicted = 3.0 + 0.5 - 1.0 * 0.05
    result = observed.step(0.0, 1.0, predicted, 1.0, allow_voltage_correction=True)
    assert result.status == "CURRENT_STEP_HOLD"
    assert result.correction == 0.0


def test_saturation_is_recorded_with_unclipped_value():
    counter = CoulombCounter(capacity_ah=2.0, soc=0.9995)
    observer = _observer(counter=counter)
    predicted = 3.0 + 0.9995
    result = observer.step(0.0, 0.0, predicted + 0.30, 1.0)
    assert result.saturated is True
    assert result.soc == 1.0
    assert result.unclipped_soc is not None and result.unclipped_soc > 1.0
    assert len(observer.saturation_events) == 1


def test_invalid_parameters_raise():
    with pytest.raises(ObserverError):
        _observer(r0_ohm=0.0)
    with pytest.raises(ObserverError):
        _observer(branches=())
    with pytest.raises(ObserverError):
        _observer(correction_time_constant_s=0.0)

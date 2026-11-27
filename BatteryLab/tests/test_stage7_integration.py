"""第七阶段端到端集成测试：真实 CALCE 数据 + 真实 ngspice，无 mock。"""

from __future__ import annotations

import numpy as np
import pytest

from experiments.common import frozen_capacity_ah, measurement_bundle
from experiments.soc_comparison import run_single_method
from experiments.spice_replay import run_spice_current_replay
from estimation.coulomb_counter import CoulombCounter
from estimation.estimation_runner import replay_coulomb_counting
from estimation.models import MeasurementSample


@pytest.fixture(scope="module")
def us06():
    return measurement_bundle("us06_50")


def test_real_calce_us06_loaded_with_reference(us06):
    assert us06["sample_count"] > 6000
    assert us06["duration_s"] > 6000.0
    reference = np.asarray(us06["reference_soc"], dtype=float)
    assert np.isfinite(reference).all()
    assert 0.0 <= reference[0] <= 1.0
    assert reference.max() <= 1.0 + 1e-6
    assert us06["source_sheet"]


def test_coulomb_counting_matches_reference_integration(us06):
    payload = run_single_method("coulomb_counting", us06)
    metrics = payload["metrics"]
    # 参考轨迹由同一电流与容量积分，允许的差异只来自浮点求和顺序。
    assert metrics["max_absolute_error_pp"] < 1e-6
    assert metrics["coverage_fraction"] > 0.99


def test_ecm_observer_meets_preregistered_targets(us06):
    payload = run_single_method("ecm_observer", us06)
    metrics = payload["metrics"]
    assert metrics["rmse_pp"] is not None and metrics["rmse_pp"] <= 3.0
    assert metrics["max_absolute_error_pp"] <= 5.0
    assert metrics["coverage_fraction"] >= 0.99
    assert metrics["voltage_prediction"]["valid_sample_count"] > 6000


def test_second_independent_profile_loads():
    bundle = measurement_bundle("bjdst_50")
    assert bundle["sample_count"] > 6000
    reference = np.asarray(bundle["reference_soc"], dtype=float)
    assert np.isfinite(reference).all()
    assert bundle["role"] == "extra_validation"


def test_data_gap_is_marked_and_not_integrated():
    samples = [
        MeasurementSample(0.0, 1.0, 3.9),
        MeasurementSample(1.0, 1.0, 3.9),
        MeasurementSample(100.0, 1.0, 3.9),
        MeasurementSample(101.0, 1.0, 3.9),
    ]
    counter = CoulombCounter(capacity_ah=2.0, soc=0.8)
    rows = replay_coulomb_counting(samples, counter, maximum_gap_s=2.0)
    assert rows[2]["status"] == "DATA_GAP"
    assert rows[2]["estimated_soc"] is None
    assert rows[3]["status"] == "RESUMED_AFTER_GAP"
    # 缺口前的 1 s 与恢复后的 1 s 被积分，缺口内 99 s 不得积分
    assert rows[3]["estimated_soc"] == pytest.approx(0.8 - 2.0 / 7200.0, abs=1e-12)


def test_real_ngspice_current_replay_charge_consistency():
    result = run_spice_current_replay("us06_50")
    assert result["spice_solve_count"] >= 1
    assert result["transient_points"] > 1000
    assert result["adc_saturation_count"] == 0
    assert result["charge_error_percent"] is not None
    assert abs(result["charge_error_percent"]) < 1.0
    assert result["current_rmse_a"] < 0.01
    assert result["source_type"] == "spice_simulation"
    # 代表性区间的 SOC 变化必须远小于容量，说明没有跨区间长期外推。
    assert abs(result["soc_error_pp"]) < 0.1

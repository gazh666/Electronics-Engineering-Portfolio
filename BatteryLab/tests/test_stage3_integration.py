"""第三阶段真实数据集成测试（CALCE + 冻结模型 + 真实 ngspice）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from battery_models.ocv_model import ConstantOcvModel
from battery_models.ecm_solver import simulate_ecm
from battery_models.states import CellState
from identification.parameter_store import load_frozen_model
from scripts.stage3_common import capacity_bundle, configs, ocv_bundle
from simulations.load_profiles import piecewise_profile
from simulations.spice_battery_runner import run_spice_single_cell
from validation.dataset_split import build_experiment

ROOT = Path(__file__).resolve().parents[1]
SECOND_ORDER_ID = "calce_sp2_25c_inr18650_20r_second_order_v1"


@pytest.mark.skipif(not (ROOT / "data" / "raw" / "SP2_Initial_capacity_10_16_2015.zip").exists(), reason="缺少 CALCE 数据")
def test_real_capacity_matches_recorded():
    capacities = capacity_bundle()
    sp2 = capacities["sp2"]
    assert sp2.integrated_capacity_ah == pytest.approx(2.0, abs=0.1)
    assert abs(sp2.capacity_difference_ah) < 1e-3
    assert sp2.points > 1000


@pytest.mark.skipif(not (ROOT / "data" / "raw" / "SP1_25C_LC_OCV_11_5_2015.zip").exists(), reason="缺少 CALCE 数据")
def test_real_ocv_table_is_monotonic_and_covers_unit_interval():
    bundle = ocv_bundle()
    soc = np.asarray(bundle["soc_table"], dtype=float)
    ocv = np.asarray(bundle["ocv_table"], dtype=float)
    assert soc[0] == 0.0 and soc[-1] == 1.0
    assert np.all(np.diff(soc) > 0)
    assert ocv[-1] > ocv[0]
    assert np.all(ocv > 2.4) and np.all(ocv < 4.3)
    assert bundle["curves"]["metrics"]["common_points"] > 100


@pytest.mark.skipif(not (ROOT / "data" / "raw" / "SP2_25C_FUDS.zip").exists(), reason="缺少 CALCE 数据")
def test_real_fuds_initial_soc():
    settings = configs()
    capacity_ah = capacity_bundle()["sp2"].integrated_capacity_ah
    fuds_50 = build_experiment("fuds_50", settings["split"]["datasets"]["fuds_50"], capacity_ah=capacity_ah)
    fuds_80 = build_experiment("fuds_80", settings["split"]["datasets"]["fuds_80"], capacity_ah=capacity_ah)
    assert fuds_50.soc0 == pytest.approx(0.5, abs=0.03)
    assert fuds_80.soc0 == pytest.approx(0.8, abs=0.03)
    assert fuds_50.soc0_method == "recorded_capacity_balance"
    assert fuds_50.frame["soc_reference"].between(-0.05, 1.05).all()


@pytest.mark.skipif(not (ROOT / "data" / "identified" / f"model_{SECOND_ORDER_ID}").exists(), reason="尚未冻结二阶模型")
def test_frozen_model_parameters_valid():
    bundle = load_frozen_model(SECOND_ORDER_ID)
    parameters = bundle["parameters"]
    assert parameters.model_order == 2
    assert parameters.r0_ohm > 0 and parameters.r1_ohm > 0 and parameters.r2_ohm > 0
    assert parameters.tau1_s < parameters.tau2_s
    assert parameters.capacity_ah == pytest.approx(2.028, abs=0.01)
    assert bundle["ocv_model"].voltage(0.5) > 3.5


@pytest.mark.skipif(not (ROOT / "data" / "identified" / f"model_{SECOND_ORDER_ID}").exists(), reason="尚未冻结二阶模型")
def test_identified_parameters_in_ngspice():
    bundle = load_frozen_model(SECOND_ORDER_ID)
    parameters = bundle["parameters"]
    definition = parameters.as_definition()
    ocv_value = bundle["ocv_model"].voltage(0.5)
    profile = piecewise_profile([(10.0, 0.0), (60.0, 2.0), (120.0, 0.0)], name="pytest_identified")
    spice = run_spice_single_cell(
        script="tests/test_stage3_integration.py",
        model_name="second_order_rc",
        parameters=definition.parameters,
        branches=definition.branches,
        ocv_v=ocv_value,
        profile=profile,
        step_s=0.05,
    )
    time_values, current_values = profile.sample(0.05)
    python_result = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.5, 2, 0.0),
        time_values,
        current_values,
        ConstantOcvModel(ocv_value),
        stop_on_limits=False,
    )
    spice_frame = spice["frame"]
    spice_time = spice_frame["time_s"].to_numpy(dtype=float)
    spice_voltage = spice_frame["terminal_voltage_v"].to_numpy(dtype=float)
    python_time = python_result.frame["time_s"].to_numpy(dtype=float)
    python_voltage = python_result.frame["terminal_voltage_v"].to_numpy(dtype=float)
    mask = np.ones(len(spice_frame), dtype=bool)
    for step_time in (10.0, 70.0):
        mask &= np.abs(spice_time - step_time) > 0.15
    interpolated = np.interp(spice_time[mask], python_time, python_voltage)
    error = np.abs(spice_voltage[mask] - interpolated)
    assert float(np.max(error)) <= 1e-3

"""第二阶段真实集成测试：ngspice、PyBaMM 与 CALCE 数据重放。

禁止使用 Mock 替代真实仿真；外部数据缺失时如实 skip。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.model_comparison import compare_frames, error_metrics
from battery_models.battery_pack import build_uniform_pack, simulate_series_pack
from battery_models.ecm_solver import simulate_ecm
from battery_models.ocv_model import ConstantOcvModel, load_ocv_reference
from battery_models.parameters import load_ecm_models
from battery_models.states import CellState
from circuits.battery_ecm_circuit import build_and_run_single_cell
from circuits.battery_pack_circuit import build_and_run_pack
from simulations.load_profiles import profile_from_frame, single_pulse_profile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def models():
    return load_ecm_models()


def test_real_ngspice_single_cell_matches_python(models) -> None:
    definition = models["second_order_rc"]
    profile = single_pulse_profile()
    _, payload = build_and_run_single_cell(
        "second_order_rc",
        definition.parameters,
        definition.branches,
        3.8,
        profile,
        step_s=0.05,
    )
    spice_frame = pd.DataFrame(payload["waveform"])
    times, currents = profile.sample(0.1)
    python = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.6, 2),
        times,
        currents,
        ConstantOcvModel(3.8),
        model_name="second_order_rc",
    )
    metrics = compare_frames(
        spice_frame,
        python.frame,
        reference_name="ngspice",
        exclude_times_s=(10.0, 70.0),
        exclude_window_s=0.15,
    )
    assert metrics["max_abs_error_v"] < 1e-3
    assert len(spice_frame) > 1000
    assert float(spice_frame["terminal_voltage_v"].iloc[0]) == pytest.approx(3.8, abs=1e-6)


def test_real_ngspice_three_series_pack(models) -> None:
    definition = models["second_order_rc"]
    profile = single_pulse_profile()
    _, payload = build_and_run_pack(
        definition.branches,
        definition.parameters.r0_ohm,
        3.8,
        profile,
        cells=3,
        step_s=0.05,
    )
    frame = pd.DataFrame(payload["waveform"])
    assert np.max(np.abs(frame["pack_voltage_v"] - frame["sum_cell_voltage_v"])) < 1e-6
    assert float(frame["pack_voltage_v"].iloc[0]) == pytest.approx(11.4, abs=1e-5)

    times, currents = profile.sample(0.1)
    python = simulate_series_pack(
        build_uniform_pack(definition, ConstantOcvModel(3.8)),
        times,
        currents,
    )
    metrics = compare_frames(
        frame,
        python["pack_frame"],
        reference_column="pack_voltage_v",
        model_column="pack_voltage_v",
        reference_name="ngspice",
        exclude_times_s=(10.0, 70.0),
        exclude_window_s=0.15,
    )
    assert metrics["max_abs_error_v"] < 1e-3


def test_real_pybamm_second_order_comparison(models) -> None:
    from battery_models.pybamm_backend import run_thevenin_teaching_case

    profile = single_pulse_profile()
    times, currents = profile.sample(0.1)
    pybamm_result = run_thevenin_teaching_case(
        capacity_ah=2.0,
        r0_ohm=0.03,
        branches=[(0.02, 1000.0), (0.015, 4000.0)],
        ocv_v=3.8,
        initial_soc=0.6,
        schedule=[(10.0, 0.0), (60.0, 2.0), (120.0, 0.0)],
        output_time_s=times,
    )
    definition = models["second_order_rc"]
    python = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.6, 2),
        times,
        currents,
        ConstantOcvModel(3.8),
        model_name="second_order_rc",
    )
    renamed = pybamm_result["frame"].rename(columns={"voltage_v": "terminal_voltage_v"})
    metrics = compare_frames(
        renamed,
        python.frame,
        reference_name="pybamm_thevenin",
        exclude_times_s=(10.0, 70.0),
        exclude_window_s=0.15,
    )
    assert metrics["max_abs_error_v"] < 2e-3
    assert float(renamed.loc[renamed["time_s"] == 70.0, "terminal_voltage_v"].iloc[0]) == pytest.approx(3.68303, abs=1e-3)


def test_calce_replay_pipeline() -> None:
    candidates = sorted(
        Path(PROJECT_ROOT).glob("results/calce/run_*/processed/*_dst.csv.gz"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        pytest.skip("未找到 CALCE DST processed 数据，公开实验重放标记 NOT_VERIFIED")
    frame = pd.read_csv(candidates[0])
    start = float(frame["time_s"].iloc[0])
    segment = frame[frame["time_s"] <= start + 1500.0]
    profile = profile_from_frame(
        segment,
        name="calce_dst_replay",
        max_gap_s=15.0,
        max_points=1200,
    )
    assert profile.time_s.size > 100
    definition = load_ecm_models()["second_order_rc"]
    result = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.6, 2),
        profile.time_s,
        profile.current_a,
        load_ocv_reference(),
        model_name="second_order_rc",
        stop_on_limits=False,
        data_source="public_experimental_data",
    )
    assert np.isfinite(result.frame["terminal_voltage_v"]).all()
    measured_time = frame["time_s"].to_numpy(dtype=float)
    measured_voltage = frame["voltage_v"].to_numpy(dtype=float)
    aligned = np.interp(profile.time_s, measured_time, measured_voltage)
    metrics = error_metrics(aligned, result.frame["terminal_voltage_v"].to_numpy(), reference_name="calce_measured")
    assert metrics["rmse_v"] < 1.0
    assert metrics["mae_v"] > 0.0

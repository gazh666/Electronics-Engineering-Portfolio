"""第一阶段集成测试：真实 PyBaMM、真实 ngspice、真实 CALCE 数据。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pybamm
import pytest

from analysis.battery_metrics import summarize_measurement
from battery_models.pybamm_backend import BatterySimulationConfig, PyBaMMBackend
from datasets.calce_loader import load_archive
from datasets.data_quality import check_frame
from storage.result_store import RunDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW = PROJECT_ROOT / "data" / "raw"


def test_spm_experiment_integration(tmp_path):
    backend = PyBaMMBackend("SPM")
    model = backend.create_model("SPM")
    upper = float(model.default_parameter_values["Upper voltage cut-off [V]"])
    experiment = pybamm.Experiment(
        [
            "Discharge at C/2 for 2 minutes",
            "Rest for 1 minute",
            f"Charge at C/2 until {upper:g} V",
        ]
    )
    config = BatterySimulationConfig(model_name="SPM", duration_s=0.0)
    result = backend.run(config, experiment=experiment)
    frame = result["waveform"]
    assert len(frame) > 5
    summary = summarize_measurement(
        frame["time_s"].to_numpy(dtype=float),
        frame["voltage_v"].to_numpy(dtype=float),
        frame["current_a"].to_numpy(dtype=float),
    )
    assert summary["discharge_capacity_ah"] > 0
    assert summary["charge_capacity_ah"] > 0

    run = RunDirectory("pybamm", root=tmp_path)
    run.write_metadata(result["metadata"])
    run.write_summary(summary)
    run.write_waveform(["time_s", "voltage_v", "current_a"], frame[["time_s", "voltage_v", "current_a"]].itertuples(index=False, name=None))
    saved = json.loads((run.path / "summary.json").read_text(encoding="utf-8"))
    assert saved["discharge_capacity_ah"] > 0
    assert (run.path / "waveform.csv").exists()


def test_thevenin_and_ngspice_available():
    backend = PyBaMMBackend("Thevenin")
    result = backend.run(BatterySimulationConfig(model_name="Thevenin", duration_s=60, output_points=20))
    assert np.isfinite(result["waveform"]["voltage_v"].to_numpy(dtype=float)).all()

    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_V, u_kOhm

    circuit = Circuit("divider")
    circuit.V("input", "vin", circuit.gnd, 5 @ u_V)
    circuit.R(1, "vin", "out", 10 @ u_kOhm)
    circuit.R(2, "out", circuit.gnd, 10 @ u_kOhm)
    analysis = circuit.simulator(temperature=25, nominal_temperature=25).operating_point()
    assert float(analysis["out"][0]) == pytest.approx(2.5, abs=1e-6)


@pytest.mark.skipif(not (RAW / "SP2_25C_DST.zip").exists(), reason="DST 数据未下载")
def test_real_calce_end_to_end():
    dataset = load_archive(RAW / "SP2_25C_DST.zip", dataset_id="it_dst", cell_id="SP2")
    report = check_frame(dataset.frame)
    assert report["status"] in {"PASS", "WARN"}
    assert dataset.frame["voltage_v"].max() < 4.5
    assert dataset.frame["current_a"].abs().max() < 6.0
    assert len(dataset.source_files) == 2

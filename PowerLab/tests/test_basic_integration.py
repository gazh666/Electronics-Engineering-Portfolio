"""第二阶段端到端集成：11 项分析、结果目录与失败记录。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import basic_circuits_demo, dc_analysis_demo
from simulations.config import load_basic_circuits_config
from storage.result_store import ResultStore


@pytest.fixture(scope="module")
def summary(tmp_path_factory):
    root = tmp_path_factory.mktemp("basic_results")
    config = load_basic_circuits_config()
    return basic_circuits_demo.run_all(config=config, store=ResultStore(root)), root


def test_all_eleven_items_pass(summary):
    payload, _ = summary
    assert payload["overall_status"] == "PASS"
    assert payload["total_items"] == 11
    assert payload["passed_items"] == 11
    assert payload["failed_items"] == 0
    assert payload["errors"] == []
    assert payload["data_source"] == {
        "waveform": "spice_simulation",
        "theory": "analytical_theory",
    }


def test_every_item_has_run_dir_and_status(summary):
    payload, root = summary
    for item in payload["items"]:
        assert item["status"] == "PASS"
        run_dir = item.get("run_dir")
        assert run_dir, f"{item['analysis']} has no run directory"
        directory = Path(run_dir)
        assert directory.parent == root
        assert (directory / "metadata.json").is_file()
        assert (directory / "circuit.cir").is_file()
        assert (directory / "waveform.csv").is_file()
        assert (directory / "summary.json").is_file()
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["status"] == "success"
        assert metadata["data_source"] == "spice_simulation"


def test_netlist_contains_analysis_command(summary):
    payload, _ = summary
    for item in payload["items"]:
        netlist = (Path(item["run_dir"]) / "circuit.cir").read_text(encoding="utf-8")
        assert any(command in netlist for command in (".op", ".dc", ".ac", ".tran"))


def test_failed_analysis_is_reported_not_faked(summary, monkeypatch):
    _, root = summary

    def boom(config=None, store=None):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(dc_analysis_demo, "analyze", boom)
    payload = basic_circuits_demo.run_all(
        config=load_basic_circuits_config(), store=ResultStore(root / "failure")
    )
    assert payload["overall_status"] == "FAIL"
    assert payload["errors"][0]["analysis"] == "voltage_divider_op_dc"
    assert payload["errors"][0]["error_type"] == "RuntimeError"
    assert any(item["status"] == "FAILED" for item in payload["items"])


def test_store_records_failure_without_waveform(tmp_path):
    store = ResultStore(tmp_path)
    directory = store.save_failure(
        analysis_name="unit_failure", error=RuntimeError("boom")
    )
    assert (directory / "metadata.json").is_file()
    assert (directory / "summary.json").is_file()
    assert (directory / "execution.log").is_file()
    assert not (directory / "waveform.csv").exists()
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["error"]["type"] == "RuntimeError"


def test_config_snapshot_roundtrip(tmp_path):
    config = load_basic_circuits_config()
    payload = config.to_dict()
    assert payload["version"] == "1.0"
    assert payload["simulation_temperature_c"] == 25.0
    assert payload["voltage_divider"]["vin_v"] == 12.0
    assert payload["rectifier"]["transient"]["end_s"] == 0.1

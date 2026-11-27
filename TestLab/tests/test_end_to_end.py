"""端到端测试：虚拟仪器 + DUT 行为模型 + 数据桥接 + 判定 + 报告。"""

from datetime import datetime
from pathlib import Path

import pytest

from engine.fault_injector import (
    FAULT_CURRENT_OFFSET,
    FAULT_DISCONNECT,
    FAULT_INTERRUPT,
    FAULT_NAN,
    FAULT_TIMEOUT,
    FAULT_VOLTAGE_OFFSET,
    LOCATION_BRIDGE,
    LOCATION_DMM_CURRENT,
    LOCATION_DMM_VOLTAGE,
    LOCATION_PSU_VOLTAGE,
    FaultInjector,
    FaultSpec,
)
from engine.test_runner import REQUIRED_RECORD_FIELDS, ScenarioTestRunner
from instruments import ElectronicLoad, InstrumentManager, PowerSupply, VirtualMultimeter
from models.virtual_dut import VirtualDUT
from reports.generator import build_report, collect_sources, save_csv, save_json

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "instruments.yaml"
CASES = ROOT / "configs" / "scenario_cases.yaml"


def _run_file(
    dut: VirtualDUT | None = None,
    fault_specs: tuple[FaultSpec, ...] = (),
) -> list[dict]:
    with InstrumentManager(CONFIG) as manager:
        psu = manager.create("psu", PowerSupply)
        dmm = manager.create("dmm", VirtualMultimeter)
        load = manager.create("load", ElectronicLoad)
        runner = ScenarioTestRunner(
            psu,
            dmm,
            load,
            dut or VirtualDUT(),
            sample_count=3,
            fault_specs=fault_specs,
        )
        return runner.run_file(CASES)


def _run_cases(
    cases: list[dict],
    fault_specs: tuple[FaultSpec, ...] = (),
):
    """返回 (records, psu, load)，便于检查异常退出后的输出状态。"""
    with InstrumentManager(CONFIG) as manager:
        psu = manager.create("psu", PowerSupply)
        dmm = manager.create("dmm", VirtualMultimeter)
        load = manager.create("load", ElectronicLoad)
        runner = ScenarioTestRunner(
            psu,
            dmm,
            load,
            VirtualDUT(),
            sample_count=3,
            max_retries=2,
            fault_specs=fault_specs,
        )
        records = runner.run_cases(cases)
        # 在释放资源前检查虚拟输出是否已关闭
        return records, psu.get_output(), load.get_input()


def _case(**overrides) -> dict:
    case = {
        "id": "TC900",
        "name": "临时用例",
        "vin": 12.0,
        "load_current": 1.0,
        "enabled": True,
        "expected_state": "NORMAL",
        "voltage_min": 4.9,
        "voltage_max": 5.1,
    }
    case.update(overrides)
    return case


def _by_id(records: list[dict], case_id: str) -> dict:
    return next(record for record in records if record["case_id"] == case_id)


# ---------------------------------------------------------------------------
# 正常流程
# ---------------------------------------------------------------------------


def test_all_twelve_cases_pass():
    records = _run_file()
    assert len(records) == 12
    for record in records:
        assert record["status"] == "PASS", record


def test_records_contain_required_fields_and_time_metadata():
    records = _run_file()
    run_ids = {record["run_id"] for record in records}
    assert len(run_ids) == 1

    for record in records:
        for field in REQUIRED_RECORD_FIELDS:
            assert field in record
        timestamp = datetime.fromisoformat(record["timestamp"])
        assert timestamp.tzinfo is not None
        assert record["duration_ms"] >= 0.0


def test_expected_protection_states_are_pass():
    records = _run_file()
    expected = {
        "TC007": "OVERCURRENT",
        "TC008": "UNDERVOLTAGE",
        "TC009": "OVERVOLTAGE",
        "TC010": "OUTPUT_OFF",
    }
    for case_id, state in expected.items():
        record = _by_id(records, case_id)
        assert record["actual_state"] == state
        assert record["expected_state"] == state
        assert record["status"] == "PASS", record
        assert record["vout"] == pytest.approx(0.0)
        assert record["voltage_status"] == "PASS"


def test_nominal_case_metrics_are_hand_calculated():
    record = _by_id(_run_file(), "TC001")
    # Vout = 5.0 - 1.0 × 0.02 = 4.98 V
    assert record["vin"] == pytest.approx(12.0)
    assert record["vout"] == pytest.approx(4.98)
    assert record["iout"] == pytest.approx(1.0)
    assert record["pout"] == pytest.approx(4.98)
    assert record["pin"] == pytest.approx(4.98 / 0.90)
    assert record["iin"] == pytest.approx(4.98 / 0.90 / 12.0)
    assert record["efficiency"] == pytest.approx(90.0)
    assert record["voltage_absolute_error_v"] == pytest.approx(0.02)
    assert record["voltage_error_percent"] == pytest.approx(0.4)


def test_input_boundary_and_full_load_cases():
    records = _run_file()
    assert _by_id(records, "TC002")["vin"] == pytest.approx(9.0)
    assert _by_id(records, "TC003")["vin"] == pytest.approx(16.0)
    full_load = _by_id(records, "TC006")
    assert full_load["iout"] == pytest.approx(2.0)
    assert full_load["vout"] == pytest.approx(4.96)
    assert full_load["status"] == "PASS"


def test_record_sources_are_explicit():
    records = _run_file()
    record = _by_id(records, "TC001")
    assert record["data_source"] == "behavioral_model"
    assert record["data_sources"] == {
        "input_voltage": "pyvisa-sim SCPI",
        "load_current": "pyvisa-sim SCPI",
        "dut_output": "behavioral_model",
        "measurement": "model(virtual_dut)+dmm_noise",
    }
    assert record["vout_measured"] == pytest.approx(record["vout"], abs=0.01)

    sources = collect_sources(records)
    assert "pyvisa-sim SCPI" in sources
    assert "behavioral_model" in sources
    assert "model(virtual_dut)+dmm_noise" in sources


# ---------------------------------------------------------------------------
# 有限重试与故障场景
# ---------------------------------------------------------------------------


def test_transient_communication_faults_are_retried():
    records = _run_file()
    for case_id in ("TC011", "TC012"):
        record = _by_id(records, case_id)
        assert record["status"] == "PASS", record
        assert record["retries"] >= 1
        triggered = [fault for fault in record["faults"] if fault["occurrences"] > 0]
        assert len(triggered) == 1
        assert triggered[0]["final_status"] == "PASS"


def test_persistent_timeout_after_retries_is_error():
    records, _, _ = _run_cases(
        [_case()],
        fault_specs=(FaultSpec(FAULT_TIMEOUT, LOCATION_BRIDGE, times=0),),
    )
    record = records[0]

    assert record["status"] == "ERROR"
    assert record["retries"] == 2
    assert "通信超时" in record["error_message"]

    fault = record["faults"][0]
    assert fault["fault_type"] == FAULT_TIMEOUT
    assert fault["location"] == LOCATION_BRIDGE
    assert fault["occurrences"] == 3  # 首次 + 2 次重试
    assert fault["retries"] == 2
    assert fault["final_status"] == "ERROR"


def test_instrument_disconnect_is_reported_and_outputs_closed():
    records, psu_output, load_input = _run_cases(
        [_case()],
        fault_specs=(FaultSpec(FAULT_DISCONNECT, LOCATION_PSU_VOLTAGE, times=0),),
    )
    record = records[0]

    assert record["status"] == "ERROR"
    assert "断开" in record["error_message"]
    assert psu_output is False
    assert load_input is False


def test_interrupted_case_closes_outputs():
    records, psu_output, load_input = _run_cases(
        [_case()],
        fault_specs=(FaultSpec(FAULT_INTERRUPT, LOCATION_BRIDGE, times=1),),
    )
    record = records[0]

    assert record["status"] == "ERROR"
    assert "TestInterrupted" in record["error_message"]
    assert psu_output is False
    assert load_input is False


def test_disabled_case_is_skipped():
    records, _, _ = _run_cases([_case(enabled=False)])
    record = records[0]
    assert record["status"] == "SKIP"
    assert "未启用" in record["error_message"]
    assert record["missing_fields"] == []


def test_invalid_parameters_are_reported_as_error():
    records, _, _ = _run_cases([_case(vin=-1.0)])
    record = records[0]
    assert record["status"] == "ERROR"
    assert "vin" in record["error_message"]


def test_efficiency_above_100_is_flagged_not_clipped():
    dut = VirtualDUT()
    with FaultInjector(dut).efficiency_override(1.2):
        record = _by_id(_run_file(dut), "TC001")

    assert record["efficiency"] == pytest.approx(120.0)
    assert record["status"] == "ERROR"
    assert any("超过物理上限" in item for item in record["data_anomalies"])


def test_voltage_measurement_offset_is_flagged():
    record = _by_id(
        _run_file(
            fault_specs=(
                FaultSpec(
                    FAULT_VOLTAGE_OFFSET,
                    LOCATION_DMM_VOLTAGE,
                    times=0,
                    value=0.2,
                ),
            )
        ),
        "TC001",
    )
    assert record["vout"] == pytest.approx(4.98)  # 模型值不受测量偏移影响
    assert record["vout_measured"] == pytest.approx(5.18, abs=0.01)
    assert record["status"] == "ERROR"
    assert any("偏差超过" in item for item in record["data_anomalies"])


def test_current_measurement_offset_is_flagged():
    record = _by_id(
        _run_file(
            fault_specs=(
                FaultSpec(
                    FAULT_CURRENT_OFFSET,
                    LOCATION_DMM_CURRENT,
                    times=0,
                    value=0.2,
                ),
            )
        ),
        "TC001",
    )
    assert record["iout"] == pytest.approx(1.0)
    assert record["iout_measured"] == pytest.approx(1.2)
    assert record["status"] == "ERROR"
    assert any("偏差超过" in item for item in record["data_anomalies"])


def test_nan_measurement_is_detected():
    record = _by_id(
        _run_file(
            fault_specs=(FaultSpec(FAULT_NAN, LOCATION_DMM_VOLTAGE, times=0),)
        ),
        "TC001",
    )
    assert record["vout_measured"] is None
    assert record["status"] == "ERROR"
    assert any("非有限" in item for item in record["data_anomalies"])
    assert all(sample is None for sample in record["dmm_samples"])


# ---------------------------------------------------------------------------
# 模型参数故障
# ---------------------------------------------------------------------------


def test_extra_dropout_fails_voltage_case():
    dut = VirtualDUT()
    with FaultInjector(dut).extra_dropout(0.2):
        record = _by_id(_run_file(dut), "TC001")
    assert record["vout"] == pytest.approx(4.78)
    assert record["status"] == "FAIL"


def test_disabled_ocp_fails_overcurrent_case():
    dut = VirtualDUT()
    with FaultInjector(dut).disable_ocp():
        record = _by_id(_run_file(dut), "TC007")
    assert record["actual_state"] == "NORMAL"
    assert record["status"] == "FAIL"


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


def test_report_files_and_summary(tmp_path):
    records = _run_file()
    report = build_report(records, run_id="run_test")
    json_path = save_json(report, tmp_path)
    csv_path = save_csv(records, report["run_id"], tmp_path)

    assert json_path.exists() and csv_path.exists()
    summary = report["summary"]
    assert summary["total"] == 12
    assert summary["PASS"] == 12
    assert summary["FAIL"] == 0
    assert summary["ERROR"] == 0
    assert summary["pass_rate_percent"] == pytest.approx(100.0)
    assert summary["all_passed"]
    assert report["environment"]["data_mode"] == "SIMULATION"

    csv_lines = csv_path.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(csv_lines) == 13  # 表头 + 12 条记录

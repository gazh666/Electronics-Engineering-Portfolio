"""TestRunner 单元测试：用假仪器/假测试台覆盖状态分支，不启用 VISA。

真实 PyVISA-sim 集成见 ``tests/test_automation_integration.py``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.performance_analyzer import PerformanceAnalyzer
from engine.models import TestCase, TestStatus
from engine.test_runner import TestRunner
from models.virtual_dut import VirtualDUT

ROOT = Path(__file__).resolve().parents[1]
LIMITS = ROOT / "configs" / "performance_limits.yaml"


def _case(**overrides) -> TestCase:
    data = dict(
        case_id="TC900",
        name="临时用例",
        category="normal",
        vin=12.0,
        input_current_limit=3.0,
        load_current=1.0,
        expected_state="NORMAL",
        limits={"vout": {"min": 4.9, "max": 5.1}},
    )
    data.update(overrides)
    return TestCase(**data)


class FakePSU:
    def __init__(self, voltage=12.0, current=3.0, output=True, stubborn=False):
        self.voltage = voltage
        self.current = current
        self.output = output
        self.stubborn = stubborn

    def set_voltage(self, value):
        if not self.stubborn:
            self.voltage = value

    def get_voltage(self):
        return self.voltage

    def set_current(self, value):
        if not self.stubborn:
            self.current = value

    def get_current(self):
        return self.current

    def set_output(self, enabled):
        self.output = enabled

    def get_output(self):
        return self.output


class BrokenCleanupPSU(FakePSU):
    def set_output(self, enabled):
        self.output = enabled

    def get_output(self):
        return True  # 永远回读为开启，模拟清理失败


class FakeLoad:
    def __init__(self, current=1.0, mode="CC", input_enabled=True):
        self.current = current
        self.mode = mode
        self.input_enabled = input_enabled

    def set_current(self, value):
        self.current = value

    def get_current(self):
        return self.current

    def set_mode(self, mode):
        self.mode = mode

    def get_mode(self):
        return self.mode

    def set_input(self, enabled):
        self.input_enabled = enabled

    def get_input(self):
        return self.input_enabled


class FakeManager:
    def __init__(self, psu=None, load=None):
        self.psu = psu or FakePSU()
        self.load = load or FakeLoad()

    def get_power_supply(self):
        return self.psu

    def get_electronic_load(self):
        return self.load


class ExplodingManager:
    def get_power_supply(self):
        raise AssertionError("SKIP 用例不应访问仪器")

    def get_electronic_load(self):
        raise AssertionError("SKIP 用例不应访问仪器")


class FakeBench:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def read_state(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class ErrorAnalyzer:
    def analyze(self, result):
        return {
            "quality_status": "ERROR",
            "quality_issues": [{"message": "效率超过 100%"}],
            "metrics": None,
        }


def _normal_result():
    return VirtualDUT().calculate(12.0, 1.0)


def _runner(psu=None, load=None, bench=None, analyzer=None):
    return TestRunner(
        FakeManager(psu, load),
        bench or FakeBench(_normal_result()),
        analyzer or PerformanceAnalyzer(LIMITS),
    )


def test_disabled_case_is_skip_without_instrument_access():
    runner = TestRunner(ExplodingManager(), FakeBench(), PerformanceAnalyzer(LIMITS))
    result = runner.run_case(_case(enabled=False), "run1")
    assert result.status is TestStatus.SKIP
    assert "未访问仪器" in result.error_message
    assert result.actual_state is None


def test_nominal_case_passes_and_keeps_raw_data():
    result = _runner().run_case(_case(), "run1")
    assert result.status is TestStatus.PASS
    assert result.actual_state == "NORMAL"
    assert result.raw_data["vout"] == pytest.approx(4.98)
    assert result.data_source == "behavioral_model"
    assert result.metrics["efficiency_percent"] == pytest.approx(90.0, rel=1e-6)
    assert {check.name for check in result.checks} == {"dut_state", "vout"}


def test_voltage_limit_failure_is_fail_with_reason():
    case = _case(limits={"vout": {"min": 5.5, "max": 5.6}})
    result = _runner().run_case(case, "run1")
    assert result.status is TestStatus.FAIL
    assert "vout" in result.error_message
    assert "超出" in result.error_message


def test_wrong_expected_state_is_fail():
    result = _runner().run_case(_case(expected_state="OVERCURRENT"), "run1")
    assert result.status is TestStatus.FAIL
    assert result.checks[0].name == "dut_state"


def test_missing_metric_is_error_not_pass():
    case = _case(
        load_current=0.0,
        load_enabled=False,
        limits={
            "vout": {"min": 4.9, "max": 5.1},
            "efficiency_percent": {"min": 85.0, "max": 100.0},
        },
    )
    bench = FakeBench(VirtualDUT().calculate(12.0, 0.0, load_enabled=False))
    result = _runner(bench=bench).run_case(case, "run1")
    assert result.status is TestStatus.ERROR
    assert "efficiency_percent" in result.error_message


def test_data_quality_error_short_circuits_checks():
    result = _runner(analyzer=ErrorAnalyzer()).run_case(_case(), "run1")
    assert result.status is TestStatus.ERROR
    assert "数据质量" in result.error_message
    assert result.checks == []


def test_setpoint_mismatch_is_error():
    stubborn = FakePSU(voltage=12.0, stubborn=True)
    bench = FakeBench(_normal_result())
    result = _runner(psu=stubborn, bench=bench).run_case(_case(vin=13.0), "run1")
    assert result.status is TestStatus.ERROR
    assert "SetpointMismatchError" in result.error_message
    assert bench.calls == 0  # 未通过设置校验时不得继续测量


def test_instrument_exception_is_error_and_cleanup_still_runs():
    psu = FakePSU()
    load = FakeLoad()
    result = _runner(
        psu=psu,
        load=load,
        bench=FakeBench(error=RuntimeError("通信中断")),
    ).run_case(_case(), "run1")
    assert result.status is TestStatus.ERROR
    assert "通信中断" in result.error_message
    assert psu.output is False
    assert load.input_enabled is False


def test_cleanup_failure_marks_error_and_flag():
    result = _runner(psu=BrokenCleanupPSU()).run_case(_case(), "run1")
    assert result.status is TestStatus.ERROR
    assert result.cleanup_failed is True
    assert "清理失败" in result.error_message


def test_result_serialization_uses_enum_strings():
    result = _runner().run_case(_case(), "run1")
    payload = result.to_dict()
    assert payload["status"] == "PASS"
    assert isinstance(payload["checks"], list)
    assert payload["checks"][0]["status"] == "PASS"


def test_execution_index_is_recorded():
    result = _runner().run_case(_case(), "run1", execution_index=7)
    assert result.execution_index == 7
    assert result.run_id == "run1"

"""数字万用表驱动测试：SCPI 测量、异常响应、超时与模型读数。"""

from pathlib import Path

import pytest

from instruments import (
    InstrumentError,
    InstrumentManager,
    InstrumentNotConnectedError,
    InstrumentResponseError,
    InstrumentTimeoutError,
    VirtualMultimeter,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "instruments.yaml"


class _StubResource:
    """最小化资源替身：只返回预设响应，用于异常分支测试。"""

    resource_name = "STUB"

    def __init__(self, responses):
        self._responses = responses
        self.timeout = None
        self.write_termination = None
        self.read_termination = None

    def query(self, command):
        return self._responses[command]

    def write(self, command):
        pass

    def close(self):
        pass


@pytest.fixture()
def dmm():
    with InstrumentManager(CONFIG) as manager:
        yield manager.create("dmm", VirtualMultimeter)


def test_identity(dmm):
    assert dmm.identify().startswith("TestLab,VirtualMultimeter,DMM001")


def test_configure_functions(dmm):
    dmm.configure_voltage()
    dmm.configure_current()


def test_measure_voltage_and_current(dmm):
    assert dmm.measure_voltage() == pytest.approx(5.0, abs=1e-4)
    assert dmm.measure_current() == pytest.approx(0.5, abs=1e-4)


def test_error_response_raises(dmm):
    with pytest.raises(InstrumentError):
        dmm.measure_bad()


def test_timeout_raises(dmm):
    dmm.set_timeout(200)
    with pytest.raises(InstrumentTimeoutError):
        dmm.measure_slow()


def test_model_reading_contains_noise(dmm):
    assert dmm.read_dc_voltage(5.0) == pytest.approx(5.0, abs=0.01)


def test_measure_resistance(dmm):
    assert dmm.measure_resistance() == pytest.approx(4.98, abs=1e-4)


def test_negative_resistance_rejected():
    dmm = VirtualMultimeter(resource=_StubResource({"MEAS:RES?": "-1.0"}))
    with pytest.raises(ValueError):
        dmm.measure_resistance()


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "abc"])
def test_invalid_voltage_response_rejected(raw):
    dmm = VirtualMultimeter(resource=_StubResource({"MEAS:VOLT?": raw}))
    with pytest.raises(InstrumentResponseError):
        dmm.measure_voltage()


def test_operations_require_connection():
    dmm = VirtualMultimeter()
    with pytest.raises(InstrumentNotConnectedError):
        dmm.measure_voltage()

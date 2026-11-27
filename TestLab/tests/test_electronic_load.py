"""电子负载驱动测试：模式、电流、输入开关与参数校验。"""

from pathlib import Path

import pytest

from instruments import (
    ElectronicLoad,
    InstrumentManager,
    InstrumentResponseError,
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
def load():
    with InstrumentManager(CONFIG) as manager:
        yield manager.create("load", ElectronicLoad)


def test_identity(load):
    assert load.identify().startswith("TestLab,VirtualElectronicLoad,LOAD001")


def test_mode_set_and_readback(load):
    load.set_mode("CC")
    assert load.get_mode() == "CC"


def test_current_set_and_readback(load):
    load.set_current(1.5)
    assert load.get_current() == pytest.approx(1.5, abs=1e-3)


def test_input_on_and_off(load):
    load.set_input(True)
    assert load.get_input() is True
    load.set_input(False)
    assert load.get_input() is False


@pytest.mark.parametrize("mode", ["XX", "", "cc "])
def test_invalid_mode_rejected(load, mode):
    with pytest.raises(ValueError):
        load.set_mode(mode)


@pytest.mark.parametrize(
    "value",
    [-0.1, 5.1, float("nan"), float("inf"), "abc"],
)
def test_invalid_current_rejected(load, value):
    with pytest.raises(ValueError):
        load.set_current(value)


def test_input_requires_bool(load):
    with pytest.raises(TypeError):
        load.set_input(1)


def test_safe_shutdown(load):
    load.set_input(True)
    load.safe_shutdown()
    assert load.get_input() is False


@pytest.mark.parametrize("mode", ["CC", "CV", "CR", "CP"])
def test_all_modes_supported(load, mode):
    load.set_mode(mode)
    assert load.get_mode() == mode


def test_current_rejected_outside_cc_mode(load):
    load.set_mode("CV")
    with pytest.raises(RuntimeError):
        load.set_current(1.0)


@pytest.mark.parametrize("current", [0.0, 5.0, 2.5])
def test_current_boundaries(load, current):
    load.set_current(current)
    assert load.get_current() == pytest.approx(current, abs=1e-3)


@pytest.mark.parametrize("raw", ["2", "1.5", "abc"])
def test_invalid_input_response_rejected(raw):
    load = ElectronicLoad(resource=_StubResource({"INP?": raw}))
    with pytest.raises(InstrumentResponseError):
        load.get_input()

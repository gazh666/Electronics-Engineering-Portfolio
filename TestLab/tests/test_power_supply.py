"""程控电源驱动测试（真实运行 @sim 后端）。"""

import math
from pathlib import Path

import pytest

from instruments import (
    InstrumentError,
    InstrumentManager,
    InstrumentNotConnectedError,
)
from instruments.power_supply import PowerSupply

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "instruments.yaml"


class _StubResource:
    """最小化 VISA 资源替身，用于构造异常回读场景（不参与真实通信）。"""

    resource_name = "STUB"

    def __init__(self, responses):
        self._responses = responses
        self.timeout = None
        self.write_termination = None
        self.read_termination = None

    def query(self, command):
        return self._responses[command]

    def write(self, command):
        raise AssertionError("异常回读用例不应写入")

    def close(self):
        pass


@pytest.fixture()
def psu():
    with PowerSupply(CONFIG) as device:
        yield device


def test_connect_and_identity(psu):
    assert psu.connected
    assert psu.identify().startswith("TestLab,VirtualPowerSupply,PS001")


def test_voltage_set_and_readback(psu):
    psu.set_voltage(12)
    assert psu.get_voltage() == pytest.approx(12.0, abs=1e-3)


def test_current_set_and_readback(psu):
    psu.set_current(2)
    assert psu.get_current() == pytest.approx(2.0, abs=1e-3)


def test_output_on_and_off(psu):
    psu.set_output(True)
    assert psu.get_output() is True
    psu.set_output(False)
    assert psu.get_output() is False


@pytest.mark.parametrize(
    "value",
    [-1, 30.001, 31, float("nan"), float("inf"), float("-inf"), "abc"],
)
def test_invalid_voltage_rejected(psu, value):
    with pytest.raises(ValueError):
        psu.set_voltage(value)


@pytest.mark.parametrize(
    "value",
    [-0.1, 5.001, 10, float("nan"), float("inf"), None, "abc", True],
)
def test_invalid_current_rejected(psu, value):
    with pytest.raises(ValueError):
        psu.set_current(value)


def test_output_requires_bool(psu):
    with pytest.raises(TypeError):
        psu.set_output(1)


def test_operations_require_connection():
    psu = PowerSupply(CONFIG)
    for operation in (
        psu.identify,
        psu.get_voltage,
        lambda: psu.set_voltage(5.0),
        psu.get_output,
        lambda: psu.set_output(True),
    ):
        with pytest.raises(InstrumentNotConnectedError):
            operation()


def test_context_manager_releases_resource():
    with PowerSupply(CONFIG) as psu:
        assert psu.connected
    assert not psu.connected
    with pytest.raises(InstrumentNotConnectedError):
        psu.get_voltage()


def test_failed_connect_releases_resources(tmp_path):
    psu = PowerSupply(tmp_path / "missing.yaml")
    with pytest.raises(FileNotFoundError):
        psu.connect()
    # 失败后不残留半开连接，重试仍应得到同样的明确错误
    with pytest.raises(FileNotFoundError):
        psu.connect()
    assert not psu.connected
    psu.close()  # 幂等关闭


def test_unknown_query_raises_instrument_error(psu):
    with pytest.raises(InstrumentError):
        psu.query("BAD:COMMAND?")


def test_infinite_values_are_rejected_before_send(psu):
    with pytest.raises(ValueError):
        psu.set_voltage(math.inf)
    # 驱动拦截后仪器仍应工作正常，未发生响应错位
    psu.set_voltage(5.0)
    assert psu.get_voltage() == pytest.approx(5.0, abs=1e-3)


def test_boolean_is_not_accepted_as_voltage(psu):
    """bool 是 int 子类，必须显式拒绝，避免 True 被当成 1 V。"""
    with pytest.raises(ValueError):
        psu.set_voltage(True)


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
def test_non_finite_readback_is_rejected(raw):
    """回读值非有限时必须报错，不能把 NaN/inf 当作有效设定值。"""
    psu = PowerSupply(resource=_StubResource({"VOLT?": raw}))
    with pytest.raises(InstrumentError):
        psu.get_voltage()


@pytest.mark.parametrize("raw", ["2", "1.5", "abc"])
def test_invalid_output_response_is_rejected(raw):
    """输出状态只接受 0/1，其他响应必须报错而不是猜测。"""
    psu = PowerSupply(resource=_StubResource({"OUTP?": raw}))
    with pytest.raises(InstrumentError):
        psu.get_output()


def test_non_numeric_readback_is_rejected():
    """回读非数字字符串时应转为 InstrumentError，而不是泄漏 ValueError。"""
    psu = PowerSupply(resource=_StubResource({"VOLT?": "abc"}))
    with pytest.raises(InstrumentError):
        psu.get_voltage()


def test_connect_is_idempotent(psu):
    """已连接时重复 connect() 不应报错，也不应重建会话。"""
    resource = psu.resource
    psu.connect()
    assert psu.resource is resource
    psu.set_voltage(12.0)
    assert psu.get_voltage() == pytest.approx(12.0, abs=1e-3)


def test_close_is_idempotent_after_connected():
    """连接后连续 close() 两次应安全，第二次无副作用。"""
    psu = PowerSupply(CONFIG)
    psu.connect()
    psu.close()
    psu.close()
    assert not psu.connected


@pytest.mark.parametrize("voltage", [0.0, 30.0, 12.345, 0.001])
def test_voltage_boundaries_and_precision(psu, voltage):
    """量程边界与 3 位小数精度应与 YAML 的格式一致。"""
    psu.set_voltage(voltage)
    assert psu.get_voltage() == pytest.approx(voltage, abs=1e-3)


@pytest.mark.parametrize("current", [0.0, 5.0, 1.234, 0.001])
def test_current_boundaries_and_precision(psu, current):
    """电流限值边界与 3 位小数精度应与 YAML 的格式一致。"""
    psu.set_current(current)
    assert psu.get_current() == pytest.approx(current, abs=1e-3)


def test_invalid_values_keep_previous_settings(psu):
    """非法参数被拦截后，之前生效的设定值必须保持不变。"""
    psu.set_voltage(12.0)
    psu.set_current(2.0)
    psu.set_output(True)

    for bad_voltage in (31, -1, float("nan")):
        with pytest.raises(ValueError):
            psu.set_voltage(bad_voltage)
    with pytest.raises(ValueError):
        psu.set_current(6)
    with pytest.raises(TypeError):
        psu.set_output("1")

    assert psu.get_voltage() == pytest.approx(12.0, abs=1e-3)
    assert psu.get_current() == pytest.approx(2.0, abs=1e-3)
    assert psu.get_output() is True


def test_closing_one_driver_keeps_shared_manager_usable():
    """关闭单个驱动后，共享 ResourceManager 仍可打开其他仪器。"""
    with InstrumentManager(CONFIG) as manager:
        psu = manager.create("psu", PowerSupply)
        psu.set_voltage(5.0)
        psu.close()
        assert not psu.connected
        assert manager.open_resource("dmm") is not None
        assert manager.open_resource("psu") is not None

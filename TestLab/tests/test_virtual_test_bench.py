"""虚拟测试台集成测试：真实 PyVISA-sim 后端 + InstrumentManager + VirtualDUT。

重点验证动态模型确实由 SCPI 回读的仪器设置驱动，而不是测试程序中
另行传入一份硬编码参数。
"""

from pathlib import Path

import pytest

from bench import VirtualTestBench
from instruments import InstrumentManager, InstrumentTimeoutError
from models.virtual_dut import DUTState, VirtualDUT

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "instruments.yaml"
DUT_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "dut_config.yaml"


@pytest.fixture()
def bench():
    with InstrumentManager(CONFIG) as manager:
        yield VirtualTestBench(manager, VirtualDUT.from_yaml(DUT_CONFIG))


def _setup(
    bench,
    vin=12.0,
    limit=2.0,
    current=1.0,
    output=True,
    load_on=True,
    mode="CC",
):
    """通过 SCPI 驱动设置工况；测试不直接向模型传参。"""
    psu = bench.psu
    load = bench.load
    psu.set_output(False)
    load.set_input(False)
    psu.set_voltage(vin)
    psu.set_current(limit)
    # 先在 CC 模式写入电流，再切换到目标模式（非 CC 模式禁止设置电流）
    load.set_mode("CC")
    load.set_current(current)
    if mode != "CC":
        load.set_mode(mode)
    psu.set_output(output)
    load.set_input(load_on)


def test_nominal_output_voltage(bench):
    _setup(bench)
    result = bench.read_state()
    assert result.state == DUTState.NORMAL
    assert result.vout == pytest.approx(4.98)


def test_full_load_lowers_output(bench):
    _setup(bench, current=2.0)
    result = bench.read_state()
    assert result.state == DUTState.NORMAL
    assert result.vout == pytest.approx(4.96)


def test_overcurrent_shuts_output_down(bench):
    _setup(bench, current=2.5)
    result = bench.read_state()
    assert result.state == DUTState.OVERCURRENT
    assert result.vout == 0.0
    assert result.iout == 0.0


def test_undervoltage_state(bench):
    _setup(bench, vin=8.0)
    assert bench.read_state().state == DUTState.UNDERVOLTAGE


def test_overvoltage_state(bench):
    _setup(bench, vin=17.0)
    assert bench.read_state().state == DUTState.OVERVOLTAGE


def test_input_current_limit_state(bench):
    _setup(bench, limit=0.1, current=1.0)
    result = bench.read_state()
    assert result.state == DUTState.INPUT_CURRENT_LIMIT
    assert result.vout == 0.0


def test_psu_output_off_zeroes_model(bench):
    _setup(bench, output=False)
    result = bench.read_state()
    assert result.state == DUTState.OUTPUT_OFF
    assert result.vin == 0.0
    assert result.vout == 0.0


def test_load_off_keeps_no_load_voltage(bench):
    _setup(bench, current=1.0, load_on=False)
    result = bench.read_state()
    assert result.state == DUTState.NORMAL
    assert result.iout == 0.0
    assert result.vout == pytest.approx(5.0)


def test_static_mock_response_unchanged(bench):
    _setup(bench, vin=15.0, current=2.0)
    static = bench.get_static_mock_measurements()
    assert static["voltage"].value == pytest.approx(5.0)
    assert static["current"].value == pytest.approx(0.5)
    assert static["voltage"].source == "static_mock"


def test_model_and_static_sources_differ(bench):
    _setup(bench)
    model = bench.get_model_measurements()
    static = bench.get_static_mock_measurements()

    assert model["voltage"].source == "behavioral_model"
    assert static["voltage"].source == "static_mock"
    assert model["voltage"].value == pytest.approx(4.98)
    assert static["voltage"].value == pytest.approx(5.0)


def test_non_cc_load_rejected(bench):
    _setup(bench, mode="CV", load_on=True)
    with pytest.raises(NotImplementedError):
        bench.read_state()


def test_communication_failure_does_not_fabricate_result(bench, monkeypatch):
    _setup(bench)

    def fail():
        raise InstrumentTimeoutError("模拟通信超时")

    monkeypatch.setattr(bench.psu, "get_voltage", fail)
    with pytest.raises(InstrumentTimeoutError):
        bench.get_model_measurements()


def test_resources_released_after_exception():
    manager = InstrumentManager(CONFIG)
    with pytest.raises(ValueError):
        with manager:
            VirtualTestBench(manager, VirtualDUT.from_yaml(DUT_CONFIG))
            raise ValueError("模拟测试中断")

    assert manager.opened_devices == {}
    assert manager.available == ()


def test_model_parameters_come_from_scpi(bench):
    """修改 SCPI 设置后模型随之变化，证明参数来自仪器回读。"""
    _setup(bench, vin=15.0, limit=3.0, current=2.0)
    reading = bench.read_snapshot()

    assert reading.vin_setpoint == pytest.approx(15.0)
    assert reading.input_current_limit == pytest.approx(3.0)
    assert reading.dut.vin == pytest.approx(15.0)
    assert reading.dut.vout == pytest.approx(4.96)
    assert reading.dut.iin == pytest.approx(4.96 * 2.0 / 0.90 / 15.0)


def test_measurement_snapshot_is_consistent(bench):
    _setup(bench)
    data = bench.get_model_measurements()
    result = data["result"]

    assert data["voltage"].value == result.vout
    assert data["current"].value == result.iout
    assert data["voltage"].source == result.source
    assert data["current"].source == result.source

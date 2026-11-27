"""DutDataBridge 数据连接层测试：仪器设定 -> 行为模型 -> 测量层。"""

from pathlib import Path

import pytest

from engine.dut_bridge import DutDataBridge
from instruments import ElectronicLoad, InstrumentManager, PowerSupply, VirtualMultimeter
from models.virtual_dut import VirtualDUT

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "instruments.yaml"


@pytest.fixture()
def rig():
    with InstrumentManager(CONFIG) as manager:
        psu = manager.create("psu", PowerSupply)
        load = manager.create("load", ElectronicLoad)
        dmm = manager.create("dmm", VirtualMultimeter)
        yield psu, load, dmm, DutDataBridge(psu, load, VirtualDUT())


def _configure(psu, load, vin=12.0, current=1.0, enabled=True):
    psu.set_voltage(vin)
    psu.set_current(2.0)
    psu.set_output(True)
    load.set_mode("CC")
    load.set_current(current)
    load.set_input(enabled)


def test_bridge_computes_model_from_instrument_setpoints(rig):
    psu, load, dmm, bridge = rig
    _configure(psu, load, vin=12.0, current=1.0)

    reading = bridge.acquire()

    assert reading.vin_setpoint == pytest.approx(12.0)
    assert reading.load_current_setpoint == pytest.approx(1.0)
    assert reading.load_input_enabled is True
    assert reading.dut.state == "NORMAL"
    assert reading.dut.vout == pytest.approx(4.98)
    assert reading.dut.efficiency == pytest.approx(0.90)
    assert reading.sources == {
        "input_voltage": "pyvisa-sim SCPI",
        "load_current": "pyvisa-sim SCPI",
        "dut_output": "behavioral_model",
    }


def test_bridge_follows_instrument_changes(rig):
    psu, load, dmm, bridge = rig
    _configure(psu, load, vin=15.0, current=2.0)

    reading = bridge.acquire()

    assert reading.dut.vin == pytest.approx(15.0)
    assert reading.dut.iout == pytest.approx(2.0)
    assert reading.dut.vout == pytest.approx(4.96)
    assert reading.dut.iin == pytest.approx(4.96 * 2.0 / 0.90 / 15.0)


def test_load_input_off_means_zero_current(rig):
    psu, load, dmm, bridge = rig
    _configure(psu, load, vin=12.0, current=1.0, enabled=False)

    reading = bridge.acquire()

    assert reading.load_current_setpoint == pytest.approx(1.0)
    assert reading.load_input_enabled is False
    assert reading.dut.iout == 0.0
    assert reading.dut.vout == pytest.approx(5.0)


def test_model_output_can_feed_measurement_layer(rig):
    psu, load, dmm, bridge = rig
    _configure(psu, load, vin=12.0, current=1.0)

    reading = bridge.acquire()
    sample = dmm.read_dc_voltage(reading.dut.vout)

    assert sample == pytest.approx(reading.dut.vout, abs=0.01)


def test_instruments_do_not_share_physical_state(rig):
    """PyVISA-sim 仪器状态相互独立：DMM 的 SCPI 读数不随电源/负载变化。"""
    psu, load, dmm, bridge = rig
    _configure(psu, load, vin=15.0, current=2.0)

    reading = bridge.acquire()
    scpi_voltage = dmm.measure_voltage()
    scpi_current = dmm.measure_current()

    # DMM 返回 YAML 中的固定模拟值，而不是 DUT 模型输出
    assert scpi_voltage == pytest.approx(5.0)
    assert scpi_current == pytest.approx(0.5)
    assert scpi_voltage != pytest.approx(reading.dut.vout)


def test_bridge_marks_output_off_when_disabled(rig):
    psu, load, dmm, bridge = rig
    _configure(psu, load, vin=12.0, current=1.0)

    reading = bridge.acquire(enabled=False)

    assert reading.dut.state == "OUTPUT_OFF"
    assert reading.dut.vout == 0.0

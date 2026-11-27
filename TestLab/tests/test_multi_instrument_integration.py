"""阶段四：多仪器协同流程、固定模拟读数与异常隔离测试。"""

from pathlib import Path

import pytest

from instruments import InstrumentError, InstrumentManager

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "instruments.yaml"


@pytest.fixture()
def manager():
    with InstrumentManager(CONFIG) as mgr:
        yield mgr


def test_multi_instrument_flow(manager):
    """电源供电、负载拉载、万用表读数的完整流程（真实 @sim 通信）。"""
    psu = manager.get_power_supply()
    dmm = manager.get_multimeter()
    load = manager.get_electronic_load()

    try:
        psu.set_voltage(5.0)
        psu.set_current(1.0)
        psu.set_output(True)

        load.set_mode("CC")
        load.set_current(1.0)
        load.set_input(True)

        assert psu.get_voltage() == pytest.approx(5.0, abs=1e-3)
        assert psu.get_current() == pytest.approx(1.0, abs=1e-3)
        assert psu.get_output() is True
        assert load.get_mode() == "CC"
        assert load.get_current() == pytest.approx(1.0, abs=1e-3)
        assert load.get_input() is True

        assert dmm.measure_voltage() == pytest.approx(5.0, abs=1e-4)
        assert dmm.measure_current() == pytest.approx(0.5, abs=1e-4)
        assert dmm.measure_resistance() == pytest.approx(4.98, abs=1e-4)
    finally:
        load.set_input(False)
        psu.set_output(False)


def test_dmm_readings_are_static_mock(manager):
    """DMM 的 SCPI 读数是固定模拟值，不随电源/负载设置变化。"""
    psu = manager.get_power_supply()
    dmm = manager.get_multimeter()
    load = manager.get_electronic_load()

    baseline = (dmm.measure_voltage(), dmm.measure_current(), dmm.measure_resistance())

    try:
        psu.set_voltage(12.0)
        psu.set_output(True)
        load.set_mode("CC")
        load.set_current(2.0)
        load.set_input(True)

        after = (dmm.measure_voltage(), dmm.measure_current(), dmm.measure_resistance())
        assert after == baseline
    finally:
        load.set_input(False)
        psu.set_output(False)


def test_invalid_parameter_does_not_affect_other_instruments(manager):
    """单台仪器参数非法只影响自身，其他仪器仍可正常通信。"""
    psu = manager.get_power_supply()
    dmm = manager.get_multimeter()
    load = manager.get_electronic_load()

    psu.set_voltage(5.0)
    with pytest.raises(ValueError):
        psu.set_voltage(31.0)

    assert psu.get_voltage() == pytest.approx(5.0, abs=1e-3)
    assert dmm.measure_voltage() == pytest.approx(5.0, abs=1e-4)
    load.set_mode("CC")
    load.set_current(0.5)
    assert load.get_current() == pytest.approx(0.5, abs=1e-3)


def test_duplicate_manager_for_same_config_rejected():
    """同一 YAML 只允许一个 ResourceManager；释放后可重新打开。"""
    mgr1 = InstrumentManager(CONFIG)
    mgr1.open()
    try:
        with pytest.raises(InstrumentError):
            InstrumentManager(CONFIG).open()
    finally:
        mgr1.close()

    mgr2 = InstrumentManager(CONFIG)
    try:
        mgr2.open()
        assert len(mgr2.discover()) == 3
    finally:
        mgr2.close()

"""阶段四：InstrumentManager 生命周期、故障清理与安全关闭测试。"""

from pathlib import Path

import pytest

from instruments import (
    BaseInstrument,
    ElectronicLoad,
    InstrumentError,
    InstrumentManager,
    PowerSupply,
    VirtualMultimeter,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "instruments.yaml"


@pytest.fixture()
def manager():
    mgr = InstrumentManager(CONFIG)
    mgr.open()
    try:
        yield mgr
    finally:
        mgr.close()


def test_discover_three_instruments(manager):
    names = manager.discover()
    assert len(names) == 3
    assert any("PS001" in n for n in names)
    assert any("DMM001" in n for n in names)
    assert any("LOAD001" in n for n in names)


def test_open_all_devices_and_identities(manager):
    psu = manager.get_power_supply()
    dmm = manager.get_multimeter()
    load = manager.get_electronic_load()

    assert isinstance(psu, PowerSupply)
    assert isinstance(dmm, VirtualMultimeter)
    assert isinstance(load, ElectronicLoad)

    assert psu.identify().startswith("TestLab,VirtualPowerSupply,PS001")
    assert dmm.identify().startswith("TestLab,VirtualMultimeter,DMM001")
    assert load.identify().startswith("TestLab,VirtualElectronicLoad,LOAD001")


def test_open_device_reuses_instance(manager):
    first = manager.get_power_supply()
    second = manager.open_device("PS001")
    assert first is second


def test_unknown_serial_rejected(manager):
    with pytest.raises(ValueError):
        manager.open_device("UNKNOWN")


def test_missing_config_file(tmp_path):
    mgr = InstrumentManager(tmp_path / "missing.yaml")
    with pytest.raises(FileNotFoundError):
        mgr.open()


def test_close_one_device_does_not_affect_others(manager):
    psu = manager.get_power_supply()
    dmm = manager.get_multimeter()
    load = manager.get_electronic_load()

    manager.close_device("PS001")
    assert not psu.connected
    assert dmm.connected
    assert load.connected
    # 其他仪器仍可正常通信
    assert dmm.measure_voltage() == pytest.approx(5.0, abs=1e-4)
    assert load.get_input() is False
    # 已关闭的仪器可以重新连接
    new_psu = manager.get_power_supply()
    assert new_psu is not psu
    new_psu.set_voltage(5.0)
    assert new_psu.get_voltage() == pytest.approx(5.0, abs=1e-3)


def test_close_unopened_device_is_noop(manager):
    manager.close_device("DMM001")
    assert manager.get_multimeter().connected


def test_device_creation_failure_releases_role_resource(manager, monkeypatch):
    class _BrokenDriver(BaseInstrument):
        def __init__(self, resource=None, **kwargs):
            raise RuntimeError("模拟驱动构造失败")

    monkeypatch.setattr(manager, "_resolve", lambda serial: ("psu", _BrokenDriver))
    with pytest.raises(RuntimeError, match="模拟驱动构造失败"):
        manager.open_device("PS001")

    # 失败后资源已释放，仍能重新创建正常驱动
    psu = manager.create("psu", PowerSupply)
    psu.set_voltage(5.0)
    assert psu.get_voltage() == pytest.approx(5.0, abs=1e-3)


def test_batch_close_safely_shuts_down_outputs(manager):
    psu = manager.get_power_supply()
    load = manager.get_electronic_load()
    psu.set_output(True)
    load.set_input(True)

    manager.close()

    assert not psu.connected
    assert not load.connected
    assert manager.available == ()


def test_close_is_idempotent(manager):
    manager.close()
    manager.close()
    assert manager.available == ()


def test_context_manager_releases_resources():
    with InstrumentManager(CONFIG) as mgr:
        mgr.get_power_supply().set_voltage(5.0)
    assert mgr.available == ()


def test_cleanup_error_does_not_mask_original_exception(manager, monkeypatch):
    def _broken_close():
        raise InstrumentError("模拟清理失败")

    monkeypatch.setattr(manager, "close", _broken_close)
    with pytest.raises(ValueError, match="原始异常"):
        with manager:
            raise ValueError("原始异常")


def test_shutdown_failure_still_releases_session(manager, monkeypatch):
    psu = manager.get_power_supply()

    def _broken_set_output(enabled):
        raise InstrumentError("模拟关断失败")

    monkeypatch.setattr(psu, "set_output", _broken_set_output)
    with pytest.raises(InstrumentError):
        manager.close_device("PS001")

    # 关断失败但会话仍被释放，且可以重新连接
    assert not psu.connected
    assert manager.get_power_supply().connected

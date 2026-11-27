"""资源发现测试：验证自定义 YAML 后端可枚举并匹配三台虚拟仪器。"""

from pathlib import Path

import pyvisa
import pytest

from instruments import (
    ElectronicLoad,
    InstrumentManager,
    PowerSupply,
    VirtualMultimeter,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "instruments.yaml"


@pytest.fixture()
def manager():
    with InstrumentManager(CONFIG) as mgr:
        yield mgr


def test_raw_pyvisa_sim_backend_lists_three_resources():
    """不经过 InstrumentManager，直接确认 ``@sim`` 后端返回 3 个资源。"""
    resource_manager = pyvisa.ResourceManager(f"{CONFIG}@sim")
    try:
        names = tuple(resource_manager.list_resources("?*::INSTR"))
    finally:
        resource_manager.close()

    assert len(names) == 3
    assert all("::INSTR" in name for name in names)
    assert any("PS001" in name for name in names)
    assert any("DMM001" in name for name in names)
    assert any("LOAD001" in name for name in names)


def test_manager_discovers_three_usb_instruments(manager):
    assert len(manager.available) == 3
    assert all("::INSTR" in name for name in manager.available)


def test_manager_matches_roles_and_identities(manager):
    psu = manager.create("psu", PowerSupply)
    dmm = manager.create("dmm", VirtualMultimeter)
    load = manager.create("load", ElectronicLoad)

    assert "PS001" in manager.resource_name("psu")
    assert "DMM001" in manager.resource_name("dmm")
    assert "LOAD001" in manager.resource_name("load")

    assert psu.identify() == "TestLab,VirtualPowerSupply,PS001,1.0.0"
    assert dmm.identify() == "TestLab,VirtualMultimeter,DMM001,1.0.0"
    assert load.identify() == "TestLab,VirtualElectronicLoad,LOAD001,1.0.0"


def test_unknown_role_rejected(manager):
    with pytest.raises(KeyError):
        manager.resource_name("scope")

"""仪器连接管理测试：资源发现、共享资源、重复连接与统一关闭。"""

from pathlib import Path

import pytest

from instruments import (
    InstrumentError,
    InstrumentManager,
    InstrumentNotConnectedError,
    PowerSupply,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "instruments.yaml"


@pytest.fixture()
def manager():
    with InstrumentManager(CONFIG) as mgr:
        yield mgr


def test_same_role_reuses_resource(manager):
    assert manager.open_resource("psu") is manager.open_resource("psu")


def test_double_open_is_safe(manager):
    manager.open()  # 已打开时重复调用不应报错
    assert len(manager.available) == 3


def test_duplicate_bind_rejected(manager):
    psu = manager.create("psu", PowerSupply)
    with pytest.raises(InstrumentError):
        psu.bind(manager.open_resource("psu"))


def test_driver_close_keeps_shared_manager_usable(manager):
    """驱动 close() 只解除自身引用，不得关闭共享的 ResourceManager。"""
    psu = manager.create("psu", PowerSupply)
    psu.set_voltage(5.0)
    psu.close()
    assert not psu.connected
    # ResourceManager 仍存活，其他角色可继续打开资源
    assert manager.open_resource("psu") is not None
    assert manager.open_resource("dmm") is not None


def test_manager_close_is_idempotent_and_blocks_use(manager):
    manager.close()
    manager.close()
    assert manager.available == ()
    with pytest.raises(RuntimeError):
        manager.open_resource("psu")


def test_driver_without_resource_cannot_operate():
    psu = PowerSupply(CONFIG)
    with pytest.raises(InstrumentNotConnectedError):
        psu.get_voltage()

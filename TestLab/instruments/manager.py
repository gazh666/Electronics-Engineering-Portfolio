"""仪器连接管理：持有唯一 ResourceManager，统一管理多台虚拟仪器。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypeVar

import pyvisa
from pyvisa.resources import MessageBasedResource

from .base import BaseInstrument
from .exceptions import InstrumentError

T = TypeVar("T", bound=BaseInstrument)

LOGGER = logging.getLogger("testlab.instruments.manager")


class InstrumentNotFoundError(RuntimeError):
    """未发现指定角色的仪器资源。"""


class InstrumentManager:
    """统一管理 ResourceManager 生命周期与仪器资源。

    - 全进程只创建调用方持有的一个 ResourceManager（始终加载 ``<yaml>@sim``）；
    - 同一角色重复打开返回同一资源，避免重复打开；
    - ``close()`` 幂等：先尽力关闭负载输入与电源输出，再释放全部资源；
    - 单台仪器关闭失败不会中断其他仪器的清理。
    """

    #: 角色 -> 资源名匹配关键字（USB 序列号）
    ROLE_KEYWORDS = {
        "psu": ("PS001",),
        "dmm": ("DMM001",),
        "load": ("LOAD001",),
    }

    #: 序列号 -> 设备类型（角色），供 open_device / get_* 使用
    DEVICE_TYPES = {
        "PS001": "psu",
        "DMM001": "dmm",
        "LOAD001": "load",
    }

    #: 进程内已打开的配置文件集合。
    #: PyVISA-sim 会缓存设备定义并共享模拟会话，同一 YAML 创建多个
    #: ResourceManager 会互相影响（关闭一个会导致另一个会话失效），
    #: 因此这里显式禁止重复打开。
    _ACTIVE_CONFIGS: set[Path] = set()

    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).resolve()
        self._rm: pyvisa.ResourceManager | None = None
        self._available: tuple[str, ...] = ()
        self._resources: dict[str, MessageBasedResource] = {}
        self._devices: dict[str, BaseInstrument] = {}
        self._registered = False

    # --- 生命周期 ---

    def __enter__(self) -> "InstrumentManager":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """退出时统一清理；清理异常不得掩盖测试中的原始异常。"""
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise
            LOGGER.exception("关闭阶段发生异常，已保留原始异常")
        return False

    def open(self) -> None:
        """加载自定义 YAML 仪器定义（``<yaml>@sim``）。重复调用无副作用。"""
        if self._rm is not None:
            return
        if not self.config_path.exists():
            raise FileNotFoundError(f"仪器定义文件不存在: {self.config_path}")
        if self.config_path in self._ACTIVE_CONFIGS:
            raise InstrumentError(
                f"配置 {self.config_path.name} 已存在打开的 InstrumentManager，"
                "请复用同一个实例"
            )
        rm = pyvisa.ResourceManager(f"{self.config_path}@sim")
        try:
            available = tuple(rm.list_resources("?*::INSTR"))
        except Exception:
            rm.close()
            raise
        self._rm = rm
        self._available = available
        self._registered = True
        self._ACTIVE_CONFIGS.add(self.config_path)
        LOGGER.info("已发现 %d 台虚拟仪器: %s", len(self._available), self._available)

    def close(self) -> None:
        """安全关闭全部仪器与资源（幂等）。

        先尝试把电子负载输入关闭、电源输出关闭，再释放会话；
        任一设备清理失败都会继续处理其他设备，最后统一抛出。
        """
        errors: list[BaseException] = []
        for serial in list(self._devices):
            try:
                self.close_device(serial)
            except Exception as exc:  # 单台失败不阻断其余仪器
                LOGGER.exception("关闭设备 %s 失败", serial)
                errors.append(exc)

        for role, resource in list(self._resources.items()):
            try:
                resource.close()
            except Exception as exc:  # 关闭阶段不中断其余资源释放
                LOGGER.exception("关闭资源 %s 失败", role)
                errors.append(exc)
        self._resources.clear()
        self._devices.clear()

        if self._rm is not None:
            try:
                self._rm.close()
            except Exception as exc:
                LOGGER.exception("关闭 ResourceManager 失败")
                errors.append(exc)
            self._rm = None
        if self._registered:
            self._ACTIVE_CONFIGS.discard(self.config_path)
            self._registered = False
        self._available = ()

        if errors:
            raise ExceptionGroup("关闭仪器时发生错误", errors)

    def _require_open(self) -> pyvisa.ResourceManager:
        if self._rm is None:
            raise RuntimeError("InstrumentManager 尚未 open()")
        return self._rm

    # --- 资源发现 ---

    @property
    def available(self) -> tuple[str, ...]:
        """当前模拟后端返回的仪器资源列表。"""
        return self._available

    def discover(self) -> list[str]:
        """返回当前后端发现的全部仪器资源名。"""
        return list(self._available)

    def resource_name(self, role: str) -> str:
        """按角色匹配资源名（psu/dmm/load）。"""
        try:
            keywords = self.ROLE_KEYWORDS[role]
        except KeyError:
            raise KeyError(f"未知仪器角色: {role}") from None

        for name in self._available:
            upper = name.upper()
            if any(keyword in upper for keyword in keywords):
                return name
        raise InstrumentNotFoundError(
            f"未找到角色 {role}。可用资源: {self._available}"
        )

    def open_resource(self, role: str) -> MessageBasedResource:
        """打开指定角色的仪器资源；同一角色只打开一次。"""
        rm = self._require_open()
        if role in self._resources:
            return self._resources[role]
        resource = rm.open_resource(self.resource_name(role))
        self._resources[role] = resource
        return resource

    def create(self, role: str, instrument_cls: type[T], **kwargs) -> T:
        """基于共享资源创建驱动对象。

        资源所有权归 Manager，驱动 close() 只解除引用，
        由 Manager.close() 统一关闭，避免重复关闭。
        """
        resource = self.open_resource(role)
        return instrument_cls(
            resource=resource,
            name=kwargs.pop("name", role),
            owns_resource=False,
            **kwargs,
        )

    # --- 按序列号管理（阶段四验收接口） ---

    @property
    def opened_devices(self) -> dict[str, BaseInstrument]:
        """已通过 open_device / get_* 打开的驱动对象。"""
        return dict(self._devices)

    def _resolve(self, serial: str) -> tuple[str, type[BaseInstrument]]:
        """序列号 -> (角色, 驱动类)；驱动类延迟导入避免循环依赖。"""
        try:
            role = self.DEVICE_TYPES[serial]
        except KeyError:
            raise ValueError(
                f"未知仪器序列号: {serial}，仅支持 {sorted(self.DEVICE_TYPES)}"
            ) from None

        if role == "psu":
            from .power_supply import PowerSupply

            return role, PowerSupply
        if role == "dmm":
            from .multimeter import Multimeter

            return role, Multimeter
        from .electronic_load import ElectronicLoad

        return role, ElectronicLoad

    def open_device(self, serial: str) -> BaseInstrument:
        """按序列号打开仪器，重复调用返回同一驱动对象。

        如果驱动构造失败，会释放本次新打开的资源，避免半开连接泄漏。
        """
        if serial in self._devices:
            return self._devices[serial]

        role, instrument_cls = self._resolve(serial)
        role_was_open = role in self._resources
        try:
            device = self.create(role, instrument_cls)
        except Exception:
            if not role_was_open:
                resource = self._resources.pop(role, None)
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        LOGGER.exception("构造失败后释放资源 %s 失败", role)
            raise
        self._devices[serial] = device
        # 供故障注入按设备编号匹配（PS001 / DMM001 / LOAD001）
        device.device_id = serial
        return device

    def get_power_supply(self):
        """打开（或复用）虚拟程控电源。"""
        return self.open_device("PS001")

    def get_multimeter(self):
        """打开（或复用）虚拟数字万用表。"""
        return self.open_device("DMM001")

    def get_electronic_load(self):
        """打开（或复用）虚拟电子负载。"""
        return self.open_device("LOAD001")

    def close_device(self, serial: str) -> None:
        """关闭单台仪器：先安全关断，再释放会话，不影响其他仪器。"""
        role = self.DEVICE_TYPES.get(serial)
        device = self._devices.pop(serial, None)
        errors: list[BaseException] = []

        if device is not None and device.connected:
            try:
                self._safe_shutdown(device)
            except Exception as exc:
                LOGGER.exception("设备 %s 安全关断失败", serial)
                errors.append(exc)
            try:
                device.close()
            except Exception as exc:
                LOGGER.exception("设备 %s 会话释放失败", serial)
                errors.append(exc)

        if role is not None:
            resource = self._resources.pop(role, None)
            if resource is not None:
                try:
                    resource.close()
                except Exception as exc:
                    LOGGER.exception("资源 %s 关闭失败", role)
                    errors.append(exc)

        if errors:
            raise InstrumentError(f"关闭设备 {serial} 时发生错误: {errors}")

    @staticmethod
    def _safe_shutdown(device: BaseInstrument) -> None:
        """按仪器类型关闭输出/输入，保证异常退出后回到安全状态。"""
        if hasattr(device, "set_input"):
            device.set_input(False)
        if hasattr(device, "set_output"):
            device.set_output(False)

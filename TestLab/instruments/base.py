"""统一仪器基类：连接管理、SCPI 收发、超时、日志与资源释放。"""

from __future__ import annotations

import logging
import math
from typing import Any

import pyvisa
from pyvisa.constants import StatusCode
from pyvisa.resources import MessageBasedResource

from .exceptions import (
    InstrumentConnectionError,
    InstrumentError,
    InstrumentNotConnectedError,
    InstrumentResponseError,
    InstrumentSessionLostError,
    InstrumentTimeoutError,
)

#: 仪器层统一日志器（默认不输出，由应用层配置 logging）
LOGGER = logging.getLogger("testlab.instruments")

#: 允许自动重试的只读查询白名单。
#:
#: 不在此列表中的查询可能有“读取并清除状态”等副作用，默认不重试；
#: 写入命令不经过本白名单，任何情况下都不会自动重试。
RETRY_SAFE_QUERIES = frozenset(
    {
        "*IDN?",
        "VOLT?",
        "CURR?",
        "OUTP?",
        "INP?",
        "MODE?",
    }
)

__all__ = [
    "BaseInstrument",
    "InstrumentConnectionError",
    "InstrumentError",
    "InstrumentNotConnectedError",
    "InstrumentResponseError",
    "InstrumentSessionLostError",
    "InstrumentTimeoutError",
    "RETRY_SAFE_QUERIES",
    "validate_number",
]


def validate_number(value: Any, label: str, low: float, high: float) -> float:
    """把输入转换为有限浮点数并做量程校验。

    在驱动层拦截非法参数，避免把越界值发给仪器后触发
    PyVISA-sim 的 ``e: "ERROR"`` 回包，造成后续响应错位。
    """
    # bool 是 int 的子类，float(True) 会得到 1.0，必须显式拒绝
    if isinstance(value, bool):
        raise ValueError(f"{label} 必须是数值，不接受布尔值 {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} 必须是数字，收到 {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须是有限数值，收到 {value!r}")
    if not low <= number <= high:
        raise ValueError(f"{label} 超出范围 {low:g}-{high:g}，收到 {number:g}")
    return number


class BaseInstrument:
    """所有 SCPI 仪器的公共基类。

    职责：
    - 绑定/释放 VISA 资源（可重复 close，不重复关闭他人资源）；
    - SCPI 写入与查询，统一把 VISA 错误转换为 InstrumentError；
    - 通信超时设置与超时异常识别；
    - 连接状态检查；
    - 记录写入/查询日志。
    """

    #: 数据来源标签
    SOURCE = "pyvisa-sim SCPI"

    def __init__(
        self,
        resource: MessageBasedResource | None = None,
        name: str = "instrument",
        timeout_ms: int = 2000,
        error_token: str = "ERROR",
        owns_resource: bool = True,
    ) -> None:
        self.name = name
        self.timeout_ms = int(timeout_ms)
        self.error_token = error_token
        self._resource: MessageBasedResource | None = None
        self._owns_resource = owns_resource
        #: 仪器编号（PS001 / DMM001 / LOAD001），供故障注入按设备匹配
        self.device_id: str | None = None
        #: 可选故障注入器与有限重试执行器（由 TestRunner 按用例注入）
        self.fault_injector: Any | None = None
        self.retry_executor: Any | None = None
        #: 会话是否已失效；失效后禁止继续使用该 SCPI 会话
        self._session_invalid = False
        if resource is not None:
            self.bind(resource, owns_resource=owns_resource)

    # --- 连接管理 ---

    @property
    def connected(self) -> bool:
        """当前是否持有可用资源。"""
        return self._resource is not None

    @property
    def is_connected(self) -> bool:
        """``connected`` 的语义化别名，便于外部状态检查。"""
        return self.connected

    @property
    def session_invalid(self) -> bool:
        """通信会话是否已失效（失效后禁止继续使用）。"""
        return self._session_invalid

    @property
    def resource(self) -> MessageBasedResource | None:
        """底层 PyVISA 资源（便于调试）。"""
        return self._resource

    def bind(self, resource: MessageBasedResource, owns_resource: bool | None = None) -> None:
        """绑定一个已打开的 VISA 资源。

        重复绑定会抛出异常，避免同一仪器被打开两次。
        """
        if self.connected:
            raise InstrumentError(f"{self.name}: 已连接，禁止重复绑定资源")
        resource.timeout = self.timeout_ms
        resource.write_termination = "\n"
        resource.read_termination = "\n"
        self._resource = resource
        self._session_invalid = False
        if owns_resource is not None:
            self._owns_resource = owns_resource
        LOGGER.info("已连接仪器 %s -> %s", self.name, resource.resource_name)

    def connect(self) -> None:
        """默认连接实现：子类可在未绑定资源时自行建立连接。"""
        if self.connected:
            return
        raise InstrumentNotConnectedError(f"{self.name}: 未提供仪器资源，无法连接")

    def close(self) -> None:
        """释放资源。

        由 InstrumentManager 创建并管理的仪器只解除引用，
        真正的资源关闭由 Manager 统一完成，避免重复关闭。
        """
        if self._resource is None:
            return
        resource = self._resource
        self._resource = None
        if self._owns_resource:
            try:
                resource.close()
            except Exception:  # 关闭阶段不掩盖原始异常
                LOGGER.exception("关闭仪器资源失败: %s", self.name)
        LOGGER.info("已释放仪器 %s", self.name)

    def set_timeout(self, timeout_ms: int) -> None:
        """设置通信超时（毫秒），用于模拟慢速/超时场景。"""
        if timeout_ms <= 0:
            raise ValueError("超时必须为正数")
        self.timeout_ms = int(timeout_ms)
        if self._resource is not None:
            self._resource.timeout = self.timeout_ms

    # --- 连接状态检查 ---

    def _require_connected(self) -> None:
        if self._resource is None:
            raise InstrumentNotConnectedError(f"{self.name}: 仪器未连接")
        if self._session_invalid:
            raise InstrumentNotConnectedError(
                f"{self.name}: 通信会话已失效，禁止继续使用（需重新建立连接）"
            )

    # --- SCPI 通信 ---

    def write(self, command: str) -> None:
        """发送不需要响应的 SCPI 命令。

        写入默认**不自动重试**：输出开启、触发测试等命令可能改变设备
        状态，重复执行不安全。故障注入只在显式配置时生效。
        """
        self._require_connected()
        try:
            if self.fault_injector is not None:
                self.fault_injector.before_write(command, device=self.device_id)
            LOGGER.debug("%s <- %s", self.name, command)
            self._resource.write(command)
        except pyvisa.errors.VisaIOError as exc:
            raise self._translate(exc, f"写入 {command!r}") from exc
        except InstrumentSessionLostError:
            self._session_invalid = True
            raise

    def query(self, command: str) -> str:
        """发送查询并返回文本响应；仪器错误回包转为异常。

        仅当调用方通过 ``retry_executor`` 且命令在
        :data:`RETRY_SAFE_QUERIES` 白名单内时才会自动重试。
        """

        def perform_query() -> str:
            if self.fault_injector is not None:
                injected = self.fault_injector.before_query(
                    command, device=self.device_id
                )
                if injected is not None:
                    return injected
            LOGGER.debug("%s ? %s", self.name, command)
            try:
                response = self._resource.query(command).strip()
            except pyvisa.errors.VisaIOError as exc:
                raise self._translate(exc, f"查询 {command!r}") from exc
            if response == self.error_token:
                raise InstrumentResponseError(
                    f"{self.name}: 仪器返回错误响应 {response!r}（命令 {command!r}）"
                )
            return response

        self._require_connected()
        try:
            if self.retry_executor is None:
                return perform_query()
            retry_safe = command.strip().upper() in RETRY_SAFE_QUERIES
            return self.retry_executor.execute(
                perform_query,
                command,
                retry_safe=retry_safe,
            )
        except InstrumentSessionLostError:
            self._session_invalid = True
            raise

    def query_float(self, command: str) -> float:
        """查询并解析为有限浮点数（拒绝 NaN 与正负无穷）。"""
        raw = self.query(command)
        try:
            value = float(raw)
        except ValueError:
            raise InstrumentResponseError(
                f"{self.name}: 响应不是数字 {raw!r}"
            ) from None
        return self._require_finite(value, raw, "有限数值")

    def query_int(self, command: str) -> int:
        """查询并解析为整数，拒绝 NaN、无穷与非整数响应。"""
        raw = self.query(command)
        try:
            value = float(raw)
        except ValueError:
            raise InstrumentResponseError(
                f"{self.name}: 响应不是整数 {raw!r}"
            ) from None
        value = self._require_finite(value, raw, "整数")
        if not value.is_integer():
            raise InstrumentResponseError(f"{self.name}: 响应不是整数 {raw!r}")
        return int(value)

    def _require_finite(self, value: float, raw: str, expected: str) -> float:
        """校验读数有限，避免把 NaN/inf 当作有效仪表数据传递下去。"""
        if not math.isfinite(value):
            raise InstrumentResponseError(f"{self.name}: 响应不是{expected} {raw!r}")
        return value

    def identify(self) -> str:
        """读取仪器身份（*IDN?）。"""
        return self.query("*IDN?")

    # --- 内部工具 ---

    def _translate(self, exc: pyvisa.errors.VisaIOError, action: str) -> InstrumentError:
        if exc.error_code == StatusCode.error_timeout:
            return InstrumentTimeoutError(f"{self.name}: {action} 超时（{self.timeout_ms} ms）")
        if exc.error_code == getattr(StatusCode, "error_connection_lost", None):
            return InstrumentSessionLostError(f"{self.name}: {action} 连接已丢失: {exc}")
        return InstrumentConnectionError(f"{self.name}: {action} 失败: {exc}")

    # --- 上下文管理 ---

    def __enter__(self) -> "BaseInstrument":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

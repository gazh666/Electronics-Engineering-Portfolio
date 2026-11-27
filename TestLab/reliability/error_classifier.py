"""异常分类：决定“是否可能恢复”，而不是根据字符串猜。

分类依据是**异常类型与 PyVISA 状态码**，不使用 ``"timeout" in str(exc)``
这类脆弱判断。默认未知异常不可重试，避免把程序缺陷当成通信抖动。
"""

from __future__ import annotations

from enum import Enum

import pyvisa
from pyvisa.constants import StatusCode

from instruments.exceptions import (
    InstrumentConnectionError,
    InstrumentNotConnectedError,
    InstrumentResponseError,
    InstrumentSessionLostError,
    InstrumentTimeoutError,
)

from .exceptions import (
    CommunicationTimeoutError,
    DeviceDisconnectedError,
    InvalidResponseError,
    RetryExhaustedError,
    UnsafeShutdownError,
)

__all__ = ["ErrorCategory", "classify_error", "is_retryable_category"]


class ErrorCategory(str, Enum):
    """异常类别。"""

    #: 阻止 pytest 把本枚举当作测试类收集
    __test__ = False

    TRANSIENT_COMMUNICATION = "TRANSIENT_COMMUNICATION"
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"
    INVALID_DATA = "INVALID_DATA"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    SHUTDOWN_ERROR = "SHUTDOWN_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


#: 可安全重试的类别（是否真正重试还要看重试策略与操作白名单）
RETRYABLE_CATEGORIES = frozenset({ErrorCategory.TRANSIENT_COMMUNICATION})

#: 视为“会话不可再用”的 PyVISA 状态码
_DISCONNECT_CODES = frozenset(
    code
    for code in (
        getattr(StatusCode, "error_connection_lost", None),
        getattr(StatusCode, "error_session_not_open", None),
        getattr(StatusCode, "error_resource_lock", None),
        getattr(StatusCode, "error_no_instrument", None),
    )
    if code is not None
)


def classify_error(exc: BaseException) -> ErrorCategory:
    """把异常分类为 :class:`ErrorCategory`。

    判定顺序很重要：先判断更具体的子类，再判断宽泛的父类。
    """
    if isinstance(exc, UnsafeShutdownError):
        return ErrorCategory.SHUTDOWN_ERROR

    if isinstance(exc, CommunicationTimeoutError):
        return ErrorCategory.TRANSIENT_COMMUNICATION

    if isinstance(exc, InstrumentTimeoutError):
        return ErrorCategory.TRANSIENT_COMMUNICATION

    if isinstance(exc, DeviceDisconnectedError):
        return ErrorCategory.DEVICE_DISCONNECTED

    if isinstance(exc, InstrumentSessionLostError):
        return ErrorCategory.DEVICE_DISCONNECTED

    if isinstance(exc, (InvalidResponseError, InstrumentResponseError)):
        return ErrorCategory.INVALID_DATA

    if isinstance(exc, RetryExhaustedError):
        # 重试耗尽本身不是可重试异常；优先沿用最后一次失败的分类
        category = getattr(exc, "category", None)
        if isinstance(category, ErrorCategory):
            return category
        return ErrorCategory.UNKNOWN_ERROR

    if isinstance(exc, pyvisa.errors.VisaIOError):
        code = getattr(exc, "error_code", None)
        if code == StatusCode.error_timeout:
            return ErrorCategory.TRANSIENT_COMMUNICATION
        if code in _DISCONNECT_CODES:
            return ErrorCategory.DEVICE_DISCONNECTED
        return ErrorCategory.UNKNOWN_ERROR

    if isinstance(exc, (InstrumentNotConnectedError, InstrumentConnectionError)):
        # 未连接/连接失败默认按“会话不可用”处理，不自动重试
        return ErrorCategory.DEVICE_DISCONNECTED

    if isinstance(exc, (ValueError, TypeError)):
        # 驱动层参数校验、配置解析错误；注意：数值解析失败在基类中已被
        # 转换为 InstrumentResponseError，不会落到这里。
        return ErrorCategory.CONFIGURATION_ERROR

    return ErrorCategory.UNKNOWN_ERROR


def is_retryable_category(category: ErrorCategory) -> bool:
    """类别层面是否允许重试（不含操作白名单判断）。"""
    return category in RETRYABLE_CATEGORIES

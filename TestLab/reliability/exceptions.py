"""可靠性实验异常层次。

设计原则
--------
- 人为注入的故障必须与真实通信故障**类型上可区分**，但又能被统一的
  ``instrument`` 异常捕获逻辑处理，避免驱动层为故障注入写第二套分支。
- 因此注入异常同时继承 :class:`InjectedFaultError` 与对应的仪器异常：
  业务层既能 ``except InstrumentTimeoutError``，也能
  ``except InjectedFaultError`` 只处理人为故障。
- 原始 PyVISA 异常链由驱动层 ``raise ... from exc`` 保留，本模块不吞掉。

重要边界
--------
本模块只用于**模拟环境**。真实仪器的通信超时、断线与本模块无关，
不得把真实失败标记为 ``InjectedFaultError``。
"""

from __future__ import annotations

from instruments.exceptions import (
    InstrumentResponseError,
    InstrumentSessionLostError,
    InstrumentTimeoutError,
)

__all__ = [
    "ReliabilityError",
    "InjectedFaultError",
    "CommunicationTimeoutError",
    "DeviceDisconnectedError",
    "InvalidResponseError",
    "RetryExhaustedError",
    "UnsafeShutdownError",
]


class ReliabilityError(RuntimeError):
    """可靠性相关基础异常。"""

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False


class InjectedFaultError(ReliabilityError):
    """人为注入的模拟故障（不是真实硬件故障）。"""


class CommunicationTimeoutError(InjectedFaultError, InstrumentTimeoutError):
    """模拟通信超时。

    同时是 :class:`instruments.exceptions.InstrumentTimeoutError`，
    因此重试执行器与仪器层可以按统一类型分类。
    """


class DeviceDisconnectedError(InjectedFaultError, InstrumentSessionLostError):
    """模拟仪器通信会话不可用（断开 / 会话丢失）。"""


class InvalidResponseError(InjectedFaultError, InstrumentResponseError):
    """模拟非法仪器响应（无法解析为有效数值）。"""


class RetryExhaustedError(ReliabilityError):
    """有限重试次数已经耗尽。

    ``category`` 保存最后一次失败的异常分类，便于上层在不解析字符串的
    前提下知道“重试耗尽前发生了什么”（例如 TRANSIENT_COMMUNICATION）。
    """

    def __init__(self, message: str, *, category: object | None = None) -> None:
        super().__init__(message)
        self.category = category


class UnsafeShutdownError(ReliabilityError):
    """模拟输出关闭未能得到确认。

    注意：本异常表示“无法确认已关闭”，不表示“已确认仍然开启”。
    上层只能记录 ``NOT_VERIFIED``，不能据此断言硬件仍带电。
    """

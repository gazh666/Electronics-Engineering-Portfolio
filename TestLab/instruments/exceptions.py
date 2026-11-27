"""TestLab 仪器异常层次。

统一异常类型，便于上层区分“连接/通信失败”和“仪器返回非法数据”。
所有异常都继承 ``InstrumentError``（``RuntimeError`` 子类），
因此旧代码中的 ``except RuntimeError`` / ``except InstrumentError`` 仍然有效。
"""

from __future__ import annotations


class InstrumentError(RuntimeError):
    """仪器业务异常基类。"""


class InstrumentResponseError(InstrumentError):
    """仪器返回了非法或错误响应（如 ``ERROR``、非数字、NaN）。"""


class InstrumentConnectionError(InstrumentError):
    """连接或通信通道异常（未连接、超时、底层 I/O 失败）。"""


class InstrumentNotConnectedError(InstrumentConnectionError):
    """在未连接状态下执行仪器操作。"""


class InstrumentSessionLostError(InstrumentConnectionError):
    """通信会话已失效（断开、连接丢失或已被关闭）。

    与 :class:`InstrumentNotConnectedError` 的区别：后者表示“从未连接”，
    本异常表示“曾经连接但当前会话不可再用”。驱动层收到本异常后必须
    标记会话失效，禁止继续复用该会话。
    """


class InstrumentTimeoutError(InstrumentConnectionError):
    """SCPI 读写超时。"""

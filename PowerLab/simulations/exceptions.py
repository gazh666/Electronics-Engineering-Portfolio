"""仿真层异常体系。

所有异常都继承 :class:`SimulationError`，并保留原始异常链，
便于命令行如实上报失败原因。
"""

from __future__ import annotations


class SimulationError(RuntimeError):
    """仿真相关错误的基类。"""


class BackendUnavailableError(SimulationError):
    """PySpice / ngspice 后端无法初始化。"""


class SimulationExecutionError(SimulationError):
    """仿真器已启动但求解失败。"""


class InvalidWaveformError(SimulationError):
    """仿真返回的波形不满足基本数据约定。"""

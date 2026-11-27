"""统一 PySpice / ngspice 共享库后端。

第一阶段已验证：PySpice 1.5 + ``ngspice-34.dll``（CFFI 共享库接口）。
这里集中管理仿真器创建、温度、版本信息与串行锁，电路文件不重复配置后端。

共享库实例在进程内复用，因此所有求解必须在 :func:`simulation_lock`
保护下串行执行。
"""

from __future__ import annotations

import importlib.metadata as metadata
import platform
import sys
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from PySpice.Spice.Netlist import Circuit
from PySpice.Spice.NgSpice.Shared import NgSpiceShared
from PySpice.Spice.Simulation import CircuitSimulation

from .exceptions import BackendUnavailableError
from .models import AnalysisType

DEFAULT_TEMPERATURE_C = 25.0
BACKEND_DESCRIPTION = "PySpice 1.5 + ngspice-34 shared DLL (CFFI)"

_SIMULATION_LOCK = threading.RLock()


@contextmanager
def simulation_lock() -> Iterator[None]:
    """串行化对共享 ngspice 实例的访问。"""
    with _SIMULATION_LOCK:
        yield


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def ngspice_version() -> int | None:
    """返回 ngspice 主版本号；无法获取时返回 ``None``。"""
    try:
        return NgSpiceShared.new_instance().ngspice_version
    except Exception:  # noqa: BLE001 - 版本查询失败不应阻断仿真
        return None


def ngspice_library_path() -> str | None:
    """返回实际加载的 ngspice 共享库路径。"""
    try:
        return NgSpiceShared.new_instance().library_path
    except Exception:  # noqa: BLE001
        return None


def backend_info() -> dict[str, Any]:
    """采集真实后端信息（版本、库路径、接口类型）。"""
    return {
        "backend": BACKEND_DESCRIPTION,
        "interface": "shared_library",
        "pyspice_version": _package_version("PySpice"),
        "ngspice_version": ngspice_version(),
        "ngspice_library": ngspice_library_path(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }


def create_simulator(circuit: Circuit, temperature_c: float = DEFAULT_TEMPERATURE_C) -> CircuitSimulation:
    """创建 PySpice 仿真器；失败时抛 :class:`BackendUnavailableError`。"""
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(temperature_c, (int, float)) or isinstance(temperature_c, bool):
        raise ValueError("temperature_c must be numeric")

    try:
        return circuit.simulator(
            temperature=float(temperature_c),
            nominal_temperature=float(temperature_c),
        )
    except Exception as exc:  # noqa: BLE001 - 后端初始化失败需要如实上报
        raise BackendUnavailableError(f"无法创建 ngspice 仿真器: {exc}") from exc


def dc_source_key(source_name: str) -> str:
    """把 ``input`` 转换为 PySpice/ngspice 需要的 ``Vinput`` 扫描键。"""
    if not isinstance(source_name, str) or not source_name.strip():
        raise ValueError("source_name must be a non-empty string")
    key = source_name.strip()
    return key if key.lower().startswith("v") else f"V{key}"


def analysis_command(
    analysis_type: AnalysisType,
    *,
    source_name: str | None = None,
    start: float | None = None,
    stop: float | None = None,
    step: float | None = None,
    start_hz: float | None = None,
    stop_hz: float | None = None,
    points_per_decade: int | None = None,
    variation: str = "dec",
    step_s: float | None = None,
    end_s: float | None = None,
    start_s: float | None = None,
    max_time_s: float | None = None,
    use_initial_condition: bool = False,
) -> str:
    """生成实际请求的分析命令文本（用于记录，不代替仿真结果）。"""
    if analysis_type is AnalysisType.OP:
        return ".op"
    if analysis_type is AnalysisType.DC:
        if source_name is None or start is None or stop is None or step is None:
            raise ValueError("DC command requires source_name/start/stop/step")
        return f".dc {dc_source_key(source_name)} {start:.12g} {stop:.12g} {step:.12g}"
    if analysis_type is AnalysisType.AC:
        if start_hz is None or stop_hz is None or points_per_decade is None:
            raise ValueError("AC command requires start/stop/points_per_decade")
        return f".ac {variation} {points_per_decade} {start_hz:.12g} {stop_hz:.12g}"
    if analysis_type is AnalysisType.TRANSIENT:
        if step_s is None or end_s is None:
            raise ValueError("transient command requires step_s/end_s")
        uic = " uic" if use_initial_condition else ""
        if max_time_s is not None:
            start_value = 0.0 if start_s is None else start_s
            return (
                f".tran {step_s:.12g} {end_s:.12g} "
                f"{start_value:.12g} {max_time_s:.12g}{uic}"
            )
        if start_s:
            return f".tran {step_s:.12g} {end_s:.12g} {start_s:.12g}{uic}"
        return f".tran {step_s:.12g} {end_s:.12g}{uic}"
    raise ValueError(f"unsupported analysis type: {analysis_type!r}")


def _add_analysis(simulator: CircuitSimulation, analysis_type: AnalysisType, **kwargs: Any) -> None:
    """把分析指令写入仿真器但不执行（用于导出完整网表）。"""
    if analysis_type is AnalysisType.OP:
        CircuitSimulation.operating_point(simulator)
    elif analysis_type is AnalysisType.DC:
        CircuitSimulation.dc(
            simulator,
            **{dc_source_key(kwargs["source_name"]): slice(kwargs["start"], kwargs["stop"], kwargs["step"])},
        )
    elif analysis_type is AnalysisType.AC:
        CircuitSimulation.ac(
            simulator,
            variation=kwargs.get("variation", "dec"),
            number_of_points=kwargs["points_per_decade"],
            start_frequency=kwargs["start_hz"],
            stop_frequency=kwargs["stop_hz"],
        )
    elif analysis_type is AnalysisType.TRANSIENT:
        transient_kwargs: dict[str, Any] = {
            "step_time": kwargs["step_s"],
            "end_time": kwargs["end_s"],
            "start_time": kwargs.get("start_s", 0.0),
        }
        if kwargs.get("max_time_s") is not None:
            transient_kwargs["max_time"] = kwargs["max_time_s"]
        if kwargs.get("use_initial_condition"):
            transient_kwargs["use_initial_condition"] = True
        CircuitSimulation.transient(simulator, **transient_kwargs)
    else:
        raise ValueError(f"unsupported analysis type: {analysis_type!r}")


def full_netlist(
    circuit: Circuit,
    analysis_type: AnalysisType,
    temperature_c: float = DEFAULT_TEMPERATURE_C,
    **kwargs: Any,
) -> str:
    """导出包含实际分析指令的完整网表（不执行仿真）。

    ``str(circuit)`` 只包含拓扑；本函数通过一个未运行的仿真器追加
    ``.op`` / ``.dc`` / ``.ac`` / ``.tran`` 与 ``.end``。
    """
    simulator = create_simulator(circuit, temperature_c)
    _add_analysis(simulator, analysis_type, **kwargs)
    return str(simulator)

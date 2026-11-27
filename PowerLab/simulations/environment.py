"""运行环境采集与 ngspice 后端真实探针。

``verify_backend`` 必须完成一次真实电路求解才能返回成功；
仅 ``import PySpice`` 不作为环境可用的依据。
"""

from __future__ import annotations

import importlib.metadata as metadata
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

from circuits.divider import build_voltage_divider, theoretical_output_voltage

PACKAGES = ("PySpice", "numpy", "scipy", "matplotlib", "pandas", "PyYAML", "cffi", "ply")


class EnvironmentError(RuntimeError):
    """仿真环境不可用。"""


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def collect_environment() -> dict[str, Any]:
    """采集解释器、平台与依赖版本。"""
    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "architecture": " ".join(platform.architecture()),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "packages": package_versions(),
        "data_source": "spice_simulation",
    }


def verify_backend() -> dict[str, Any]:
    """用 12 V 分压电路做一次真实 ngspice 求解。

    返回真实节点电压；若后端未初始化或结果明显错误，抛 ``EnvironmentError``。
    """
    circuit = build_voltage_divider()
    try:
        simulator = circuit.simulator(temperature=25, nominal_temperature=25)
        operating_point = simulator.operating_point()
        vin = float(operating_point["vin"][0])
        vout = float(operating_point["out"][0])
    except Exception as exc:  # noqa: BLE001 - 环境探针需要如实上报所有异常
        raise EnvironmentError(f"ngspice 后端初始化或求解失败: {exc}") from exc

    expected = theoretical_output_voltage()
    if abs(vin - 12.0) > 1e-6:
        raise EnvironmentError(f"输入节点电压异常: {vin}")
    if abs(vout - expected) > 1e-6:
        raise EnvironmentError(f"分压输出异常: 仿真 {vout} V，理论 {expected} V")

    return {
        "backend": "PySpice 1.5 + ngspice-34 shared DLL",
        "probe_circuit": "voltage_divider",
        "simulated_vin_v": vin,
        "simulated_vout_v": vout,
        "theoretical_vout_v": expected,
        "netlist": str(circuit),
        "status": "OK",
    }


def check_results_writable(results_root: str | Path) -> Path:
    """确认结果目录可写，返回实际写入并删除的临时文件路径。"""
    root = Path(results_root)
    root.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="_write_probe_", suffix=".tmp", dir=root, delete=False
    )
    probe = Path(handle.name)
    try:
        handle.write("PowerLab write probe\n")
        handle.flush()
    finally:
        handle.close()
    probe.unlink(missing_ok=True)
    return probe

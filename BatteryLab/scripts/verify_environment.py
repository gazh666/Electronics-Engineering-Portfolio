"""BatteryLab 环境验证。

要求真实执行 PyBaMM 数值求解与 ngspice 电路求解，两个后端分别判定。
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from storage.result_store import RunDirectory

PASS = "PASS"
FAIL = "FAIL"
NOT_VERIFIED = "NOT_VERIFIED"

PACKAGES = ["pybamm", "numpy", "scipy", "pandas", "matplotlib", "openpyxl", "PyYAML", "requests", "PySpice"]


def _check(checks: list[dict[str, Any]], name: str, status: str, detail: str, **extra: Any) -> None:
    entry = {"name": name, "status": status, "detail": detail}
    entry.update(extra)
    checks.append(entry)


def check_python(checks: list[dict[str, Any]]) -> None:
    version = platform.python_version()
    ok = sys.version_info[:2] == (3, 11)
    _check(checks, "python_version", PASS if ok else FAIL, f"Python {version}", version=version)


def check_packages(checks: list[dict[str, Any]]) -> None:
    for package in PACKAGES:
        try:
            version = importlib.metadata.version(package)
            _check(checks, f"package_{package}", PASS, version, version=version)
        except importlib.metadata.PackageNotFoundError:
            _check(checks, f"package_{package}", FAIL, "未安装")


def check_pybamm_real_solve(checks: list[dict[str, Any]]) -> None:
    """真实 PyBaMM 求解（非仅 import）。"""
    try:
        import pybamm

        model = pybamm.lithium_ion.SPM()
        simulation = pybamm.Simulation(model)
        solution = simulation.solve([0, 60])
        voltage = np.asarray(solution["Voltage [V]"].entries, dtype=float).squeeze()
        current = np.asarray(solution["Current [A]"].entries, dtype=float).squeeze()
        if voltage.size < 2 or not np.isfinite(voltage).all() or not np.isfinite(current).all():
            _check(checks, "pybamm_real_solve", FAIL, "求解结果为空或含非有限值")
            return
        _check(
            checks,
            "pybamm_real_solve",
            PASS,
            f"SPM 60s 求解成功，V_end={voltage[-1]:.6f} V, I={current[0]:.6f} A",
            solver=type(simulation.solver).__name__,
            voltage_end_v=float(voltage[-1]),
            current_a=float(current[0]),
        )
    except Exception as exc:  # noqa: BLE001 - 环境检查必须捕获全部异常
        _check(checks, "pybamm_real_solve", FAIL, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()


def check_solver(checks: list[dict[str, Any]]) -> None:
    try:
        import pybamm

        model = pybamm.lithium_ion.SPM()
        simulation = pybamm.Simulation(model)
        solver_name = type(simulation.solver).__name__
        _check(checks, "pybamm_solver", PASS, solver_name, solver=solver_name)
    except Exception as exc:  # noqa: BLE001
        _check(checks, "pybamm_solver", FAIL, f"{type(exc).__name__}: {exc}")


def check_pyspice_import(checks: list[dict[str, Any]]) -> None:
    try:
        import PySpice

        _check(checks, "pyspice_import", PASS, f"PySpice {PySpice.__version__}")
    except Exception as exc:  # noqa: BLE001
        _check(checks, "pyspice_import", FAIL, f"{type(exc).__name__}: {exc}")


def check_ngspice(checks: list[dict[str, Any]]) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        from PySpice.Spice.NgSpice.Shared import NgSpiceShared

        shared = NgSpiceShared.new_instance()
        info["ngspice_version"] = int(shared.ngspice_version)
        info["ngspice_library"] = str(shared.library_path)
        _check(checks, "ngspice_library", PASS, f"ngspice {info['ngspice_version']} @ {info['ngspice_library']}")
    except Exception as exc:  # noqa: BLE001
        _check(checks, "ngspice_library", NOT_VERIFIED, f"{type(exc).__name__}: {exc}")
        info["ngspice_error"] = str(exc)
    return info


def check_spice_real_solve(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """真实 ngspice 电阻分压（5V -> 2.5V）。"""
    result: dict[str, Any] = {}
    try:
        from PySpice.Spice.Netlist import Circuit
        from PySpice.Unit import u_V, u_kOhm

        circuit = Circuit("BatteryLab divider")
        circuit.V("input", "vin", circuit.gnd, 5 @ u_V)
        circuit.R(1, "vin", "out", 10 @ u_kOhm)
        circuit.R(2, "out", circuit.gnd, 10 @ u_kOhm)
        simulator = circuit.simulator(temperature=25, nominal_temperature=25)
        analysis = simulator.operating_point()
        vout = float(analysis["out"][0])
        result["vout_v"] = vout
        result["theory_v"] = 2.5
        result["abs_error_v"] = abs(vout - 2.5)
        status = PASS if abs(vout - 2.5) < 1e-6 else FAIL
        _check(
            checks,
            "ngspice_real_solve",
            status,
            f"分压输出 {vout:.9f} V（理论 2.5 V，误差 {abs(vout - 2.5):.3e} V）",
            **result,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        _check(checks, "ngspice_real_solve", NOT_VERIFIED, f"{type(exc).__name__}: {exc}")
        return result


def check_directories(checks: list[dict[str, Any]]) -> None:
    for relative in ("data/raw", "data/processed", "results"):
        directory = PROJECT_ROOT / relative
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=True) as handle:
                handle.write(b"batterylab")
                handle.flush()
            _check(checks, f"dir_writable_{relative}", PASS, str(directory))
        except Exception as exc:  # noqa: BLE001
            _check(checks, f"dir_writable_{relative}", FAIL, f"{type(exc).__name__}: {exc}")


def summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {PASS: 0, FAIL: 0, NOT_VERIFIED: 0}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    pybamm_status = PASS
    for check in checks:
        if check["name"].startswith("pybamm") and check["status"] != PASS:
            pybamm_status = check["status"]
    spice_status = PASS
    for check in checks:
        if check["name"].startswith("ngspice") and check["status"] != PASS:
            spice_status = check["status"]
    return {
        "counts": counts,
        "pybamm_backend_status": pybamm_status,
        "ngspice_backend_status": spice_status,
        "overall_status": FAIL if counts[FAIL] else (NOT_VERIFIED if counts[NOT_VERIFIED] else PASS),
    }


def main() -> int:
    checks: list[dict[str, Any]] = []
    check_python(checks)
    check_packages(checks)
    check_pyspice_import(checks)
    check_pybamm_real_solve(checks)
    check_solver(checks)
    ngspice_info = check_ngspice(checks)
    spice_result = check_spice_real_solve(checks)
    check_directories(checks)

    summary = summarize(checks)
    run = RunDirectory("stage1")
    payload = {
        "data_source": "environment_check",
        "project_root": str(PROJECT_ROOT),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "checks": checks,
        "summary": summary,
        "ngspice": ngspice_info,
        "spice_divider": spice_result,
    }
    run.write_metadata({"script": "scripts/verify_environment.py", "kind": "environment"})
    run.write_summary(payload)
    print(json.dumps({"run_id": run.run_id, "path": str(run.path), **summary}, ensure_ascii=False, indent=2))
    for check in checks:
        print(f"[{check['status']:>12}] {check['name']}: {check['detail']}")
    return 0 if summary["overall_status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())

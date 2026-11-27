"""三项目注册表：真实路径、Git 状态、环境版本与核心入口核查。

所有结论来自本机实际目录与子进程输出；目录不存在、Git 不可用、版本文件缺失
都如实返回，不补任何默认值。
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from battery_models.parameters import PROJECT_ROOT, load_yaml

CONFIG_PATH = PROJECT_ROOT / "configs" / "project_paths.yaml"

CORE_ENTRIES = {
    "testlab": [
        "engine/result_judge.py",
        "engine/test_runner.py",
        "engine/suite_runner.py",
        "instruments/manager.py",
        "bench/virtual_test_bench.py",
        "configs/test_cases.yaml",
        "VERSION",
    ],
    "powerlab": [
        "circuits/buck.py",
        "circuits/nonideal_buck.py",
        "circuits/closed_loop_buck.py",
        "control/pi_controller.py",
        "control/averaged_buck.py",
        "control/spice_controller.py",
        "analysis/power_metrics.py",
        "analysis/transient_metrics.py",
    ],
    "batterylab": [
        "battery_models/battery_pack.py",
        "protection/protection_controller.py",
        "circuits/battery_ecm_circuit.py",
        "simulations/spice_battery_runner.py",
        "docs/90_stage8_final_validation.md",
    ],
}


def load_project_paths(path: str | Path | None = None) -> dict[str, Any]:
    payload = load_yaml(path or CONFIG_PATH)
    projects = payload.get("projects")
    if not isinstance(projects, dict):
        raise ValueError("project_paths.yaml 缺少 projects 映射")
    return dict(projects)


def _git(root: Path) -> dict[str, Any]:
    """读取 Git 状态；非 Git 仓库明确返回 not_a_repository。"""
    if not (root / ".git").exists():
        return {"status": "NOT_A_GIT_REPOSITORY"}
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=20,
        )
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=20,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
        return {"status": "GIT_ERROR", "error": f"{type(exc).__name__}: {exc}"}
    dirty = [line for line in status.stdout.splitlines() if line.strip()]
    return {
        "status": "GIT_OK",
        "head": head.stdout.strip() or None,
        "branch": branch.stdout.strip() or None,
        "dirty_file_count": len(dirty),
        "dirty_sample": dirty[:10],
    }


def _python_version(env_name: str) -> dict[str, Any]:
    try:
        from integration.environment_adapter import find_conda

        conda = find_conda()
        process = subprocess.run(
            [conda, "run", "--no-capture-output", "-n", env_name, "python", "-V"],
            capture_output=True, text=True, timeout=120,
        )
        text = (process.stdout or "").strip() or (process.stderr or "").strip()
        return {
            "status": "OK" if process.returncode == 0 else "NONZERO",
            "version": text,
            "returncode": process.returncode,
        }
    except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def _key_files(root: Path, entries: list[str]) -> dict[str, Any]:
    present = [entry for entry in entries if (root / entry).exists()]
    missing = [entry for entry in entries if not (root / entry).exists()]
    return {"present": present, "missing": missing, "coverage": len(present) / max(len(entries), 1)}


def _read_text(path: Path, limit: int = 400) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit].strip()
    except OSError:
        return None


def _module_count(root: Path, package: str) -> int:
    directory = root / package
    if not directory.is_dir():
        return 0
    return len([p for p in directory.glob("*.py") if p.is_file()])


def inspect_project(name: str, info: dict[str, Any]) -> dict[str, Any]:
    root = Path(str(info.get("root", ""))).resolve()
    exists = root.is_dir()
    payload: dict[str, Any] = {
        "name": name,
        "root": str(root),
        "exists": exists,
        "conda_env": info.get("conda_env"),
        "read_only_source": bool(info.get("read_only_source", True)),
        "git": {"status": "NOT_CHECKED"},
        "python": {"status": "NOT_CHECKED"},
        "key_files": {"present": [], "missing": CORE_ENTRIES.get(name, [])},
        "module_counts": {},
        "version_file": None,
    }
    if not exists:
        return payload
    payload["git"] = _git(root)
    payload["python"] = _python_version(str(info.get("conda_env", "base")))
    payload["key_files"] = _key_files(root, CORE_ENTRIES.get(name, []))
    for package in ("analysis", "circuits", "control", "engine", "instruments", "simulations",
                    "validation", "protection", "battery_models", "estimation", "health",
                    "integration", "system_models"):
        count = _module_count(root, package)
        if count:
            payload["module_counts"][package] = count
    version_text = _read_text(root / "VERSION", 80)
    if version_text:
        payload["version_file"] = version_text
    if name == "batterylab":
        payload["battery_packages"] = sorted(payload["module_counts"])
    return payload


def inspect_all(path: str | Path | None = None) -> dict[str, Any]:
    projects = load_project_paths(path)
    records = {name: inspect_project(name, info) for name, info in projects.items()}
    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "host": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "numpy": _pkg_version("numpy"),
            "pandas": _pkg_version("pandas"),
            "scipy": _pkg_version("scipy"),
            "pyspice": _pkg_version("PySpice"),
        },
        "projects": records,
        "all_present": all(record["exists"] for record in records.values()),
        "all_key_files_present": all(
            not record["key_files"].get("missing") for record in records.values()
        ),
    }


def _pkg_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def write_manifest(payload: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


__all__ = [
    "CORE_ENTRIES",
    "inspect_all",
    "inspect_project",
    "load_project_paths",
    "write_manifest",
]

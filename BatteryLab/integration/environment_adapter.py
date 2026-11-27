"""跨项目只读调用封装。

参考实现来自第九阶段规格 Task 4，并增加两项工程约束：

1. 执行前后对目标项目源码与历史结果做哈希快照，用于证明"未修改其他项目"；
2. 对已知会写文件的入口给出显式警告，禁止在原始目录直接运行写操作脚本。

本模块不会自动获得写隔离能力；调用方必须先确认被调用模块的写入行为。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

HASH_EXTENSIONS = (".py", ".yaml", ".yml", ".json", ".md", ".toml", ".txt", ".cir", ".cfg")
SKIP_DIRECTORIES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "results",
    "htmlcov",
    "node_modules",
    ".streamlit",
    ".mypy_cache",
}


def find_conda() -> str:
    conda = shutil.which("conda.exe") or shutil.which("conda")
    if conda is None:
        raise FileNotFoundError("Conda executable not found")
    return conda


def run_project_module(
    project_root: str | Path,
    conda_env: str,
    module_name: str,
    arguments: Sequence[Any] = (),
    *,
    timeout_s: float = 180,
    working_directory: str | Path | None = None,
) -> dict[str, Any]:
    """在指定 conda 环境执行目标项目的 ``python -m <module>``。"""
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    cwd = Path(working_directory or root).resolve()
    if not cwd.is_dir():
        raise FileNotFoundError(cwd)
    command = [
        find_conda(),
        "run",
        "--no-capture-output",
        "-n",
        conda_env,
        "python",
        "-B",
        "-m",
        module_name,
        *map(str, arguments),
    ]
    started = time.perf_counter()
    try:
        process = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            shell=False,
        )
        return {
            "command": command,
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "duration_s": time.perf_counter() - started,
            "status": "COMMAND_OK" if process.returncode == 0 else "COMMAND_NONZERO",
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "returncode": None,
            "status": "TIMEOUT",
            "duration_s": time.perf_counter() - started,
        }


def run_python_script(
    conda_env: str,
    script_path: str | Path,
    arguments: Sequence[Any] = (),
    *,
    working_directory: str | Path,
    timeout_s: float = 180,
    extra_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """直接运行一个脚本文件（用于只读桥接脚本，不经 ``-m``）。"""
    import os

    script = Path(script_path).resolve()
    if not script.is_file():
        raise FileNotFoundError(script)
    cwd = Path(working_directory).resolve()
    command = [
        find_conda(),
        "run",
        "--no-capture-output",
        "-n",
        conda_env,
        "python",
        "-B",
        str(script),
        *map(str, arguments),
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = ""
    if extra_environment:
        environment.update(extra_environment)
    started = time.perf_counter()
    try:
        process = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            shell=False,
            env=environment,
        )
        return {
            "command": command,
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "duration_s": time.perf_counter() - started,
            "status": "COMMAND_OK" if process.returncode == 0 else "COMMAND_NONZERO",
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "returncode": None,
            "status": "TIMEOUT",
            "duration_s": time.perf_counter() - started,
        }


def hash_tree(root: str | Path, *, extensions: Iterable[str] = HASH_EXTENSIONS) -> dict[str, str]:
    """对目录内源码与配置做 SHA-256 快照；跳过 results、缓存与版本库目录。"""
    base = Path(root)
    allowed = tuple(extensions)
    digests: dict[str, str] = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(base).parts
        if any(part in SKIP_DIRECTORIES for part in relative_parts):
            continue
        if path.suffix.lower() not in allowed:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digests[str(path.relative_to(base)).replace("\\", "/")] = digest
    return digests


def compare_snapshots(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    """比较两份哈希快照，输出新增/删除/修改文件。"""
    before_keys = set(before)
    after_keys = set(after)
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    changed = sorted(key for key in before_keys & after_keys if before[key] != after[key])
    return {
        "unchanged": not (added or removed or changed),
        "added": added,
        "removed": removed,
        "changed": changed,
        "file_count_before": len(before),
        "file_count_after": len(after),
    }


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


__all__ = [
    "HASH_EXTENSIONS",
    "SKIP_DIRECTORIES",
    "compare_snapshots",
    "find_conda",
    "hash_tree",
    "run_project_module",
    "run_python_script",
    "write_json",
]

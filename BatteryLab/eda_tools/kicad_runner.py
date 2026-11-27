"""KiCad CLI 定位与命令执行。

限制：
- COMMAND_OK 只表示进程正常退出，不代表 ERC/DRC 合格；
- 每次检查必须写入新的 Run ID 目录，禁止复用旧报告；
- 本模块不负责解析报告，解析见 report_parser。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_INSTALL_ROOT = Path(r"C:\Program Files\KiCad")


def find_kicad_cli(configured_path: str | None = None) -> str:
    """按 显式路径 → PATH → 安装根目录 的顺序定位 kicad-cli。"""
    if configured_path:
        path = Path(configured_path)
        if path.is_file():
            return str(path.resolve())
        raise FileNotFoundError(configured_path)

    executable = shutil.which("kicad-cli")
    if executable:
        return executable

    root = DEFAULT_INSTALL_ROOT
    if root.is_dir():
        candidates = sorted(root.glob("*/bin/kicad-cli.exe"))
        if len(candidates) == 1:
            return str(candidates[0])
        if len(candidates) > 1:
            raise RuntimeError(
                "Multiple KiCad versions found; configure explicit executable"
            )

    raise FileNotFoundError("KiCad CLI not found")


def run_kicad_command(
    executable: str,
    arguments: list,
    output_directory: str | Path,
    task_name: str,
    timeout_s: float = 180,
) -> dict:
    """执行一条 kicad-cli 命令并把原始结果写入 <task_name>.json。"""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    command = [str(executable), *map(str, arguments)]
    started = time.perf_counter()

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            shell=False,
        )
        result = {
            "task": task_name,
            "command": command,
            "returncode": process.returncode,
            "duration_s": time.perf_counter() - started,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "status": "COMMAND_OK" if process.returncode == 0 else "COMMAND_NONZERO",
        }
    except subprocess.TimeoutExpired:
        result = {
            "task": task_name,
            "command": command,
            "returncode": None,
            "duration_s": time.perf_counter() - started,
            "status": "TIMEOUT",
        }
    except OSError as exc:
        result = {
            "task": task_name,
            "command": command,
            "returncode": None,
            "status": "EXECUTION_ERROR",
            "error": str(exc),
        }

    report_path = output / f"{task_name}.json"
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return result


def probe_cli_help(executable: str, groups: list[list[str]], output_directory: str) -> dict:
    """逐个执行 --help，记录本机真实支持的子命令与参数。"""
    results = {}
    for index, group in enumerate(groups):
        results[" ".join(group)] = run_kicad_command(
            executable,
            [*group, "--help"],
            output_directory,
            f"help_{index:02d}_" + "_".join(group).replace(" ", "_"),
            timeout_s=60,
        )
    return results

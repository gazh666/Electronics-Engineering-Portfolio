"""检测本机 KiCad 环境并记录真实结果。

不安装、不提权、不修改系统设置。找不到时明确输出 KICAD_NOT_FOUND 与安装步骤。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from eda_tools import kicad_runner

HELP_GROUPS = [
    ["version"],
    ["sch", "erc"],
    ["sch", "export", "netlist"],
    ["sch", "export", "bom"],
    ["sch", "export", "pdf"],
    ["pcb", "drc"],
    ["pcb", "export", "gerbers"],
    ["pcb", "export", "drill"],
    ["pcb", "export", "pos"],
    ["pcb", "export", "step"],
    ["pcb", "export", "svg"],
]

INSTALL_STEPS = [
    "1. 打开 https://www.kicad.org/download/windows/ 下载官方安装程序，或执行：",
    "   winget install --id KiCad.KiCad --accept-package-agreements --accept-source-agreements",
    "2. 安装时勾选符号库、封装库与 3D 模型库（默认即包含）。",
    "3. 安装完成后确认：C:\\Program Files\\KiCad\\<版本>\\bin\\kicad-cli.exe version",
    "4. 需要 pcbnew Python 接口时，使用 KiCad 自带 Python（不要从 PyPI 安装同名 pcbnew）。",
    "5. 重新运行：python -m scripts.verify_kicad --cli \"C:\\Program Files\\KiCad\\<版本>\\bin\\kicad-cli.exe\"",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="KiCad 环境检测")
    parser.add_argument("--cli", default=None, help="显式指定 kicad-cli.exe 路径")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else Path("results/eda") / f"run_kicad_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "configured_path": args.cli,
    }

    try:
        executable = kicad_runner.find_kicad_cli(args.cli)
    except (FileNotFoundError, RuntimeError) as exc:
        report.update(
            {
                "status": "KICAD_NOT_FOUND",
                "error": str(exc),
                "install_steps": INSTALL_STEPS,
                "note": "原理图与 PCB 相关任务保留 BLOCKED，不生成虚假完成证据",
            }
        )
        (output_dir / "kicad_env.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("KiCad 未找到：KICAD_NOT_FOUND")
        print(f"  报告: {output_dir / 'kicad_env.json'}")
        for line in INSTALL_STEPS:
            print("  " + line)
        return 0

    report["executable"] = executable

    version = kicad_runner.run_kicad_command(
        executable, ["version"], output_dir, "kicad_version", timeout_s=60
    )
    report["version_stdout"] = version.get("stdout", "").strip()
    report["version_returncode"] = version.get("returncode")

    helps = {}
    for group in HELP_GROUPS:
        result = kicad_runner.run_kicad_command(
            executable,
            [*group, "--help"],
            output_dir,
            "help_" + "_".join(group),
            timeout_s=60,
        )
        helps[" ".join(group)] = {
            "returncode": result.get("returncode"),
            "status": result.get("status"),
            "stdout_head": (result.get("stdout") or "")[:1500],
        }
    report["help_probe"] = helps
    report["status"] = "KICAD_FOUND"

    (output_dir / "kicad_env.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"KiCad 已找到: {executable}")
    print(f"  version: {report['version_stdout']}")
    print(f"  报告: {output_dir / 'kicad_env.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

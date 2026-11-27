"""PCB DRC 与板级指标审计。

没有 KiCad / PCB 文件时输出 BLOCKED，并给出需要用户完成的操作。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from eda_tools import board_metrics, kicad_runner, report_parser

BMS_PCB = Path("hardware/eda/BatteryLab_BMS_V1/BatteryLab_BMS_V1.kicad_pcb")
CHG_PCB = Path("hardware/eda/BatteryLab_Charger_V1/BatteryLab_Charger_V1.kicad_pcb")


def audit_board(name: str, pcb_path: Path, output_dir: Path, cli: str | None) -> dict:
    report: dict = {"project": name, "pcb": str(pcb_path)}

    if not pcb_path.is_file():
        report["status"] = "BLOCKED_NO_PCB"
        report["reason"] = "PCB 文件不存在（本机无 KiCad GUI，未完成 PCB 布局布线）"
        return report

    if cli is None:
        report["status"] = "BLOCKED_NO_KICAD"
        return report

    drc_path = output_dir / f"{name}_drc_raw.json"
    drc = kicad_runner.run_kicad_command(
        cli,
        [
            "pcb", "drc",
            "--format", "json",
            "--severity-all",
            "--schematic-parity",
            "--exit-code-violations",
            "--output", str(drc_path),
            str(pcb_path),
        ],
        output_dir,
        f"{name}_drc",
        timeout_s=300,
    )
    report["drc_command"] = {"returncode": drc.get("returncode"), "status": drc.get("status")}

    if not drc_path.is_file():
        report["status"] = "BLOCKED_DRC_REPORT_MISSING"
        return report

    summary = report_parser.summarize_report(drc_path)
    (output_dir / f"{name}_drc_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report["drc_summary"] = summary

    if board_metrics.pcbnew_available():
        try:
            metrics = board_metrics.extract_board_metrics(pcb_path)
            (output_dir / f"{name}_board_metrics.json").write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            report["board_metrics"] = metrics
        except Exception as exc:  # pcbnew 版本差异
            report["board_metrics_error"] = str(exc)
    else:
        report["board_metrics_error"] = "pcbnew 不可用（需要 KiCad 自带 Python）"

    report["status"] = "AUDITED"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="PCB DRC 审计")
    parser.add_argument("--cli", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else Path("results/eda") / f"run_pcb_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    cli = None
    try:
        cli = kicad_runner.find_kicad_cli(args.cli)
    except (FileNotFoundError, RuntimeError):
        cli = None

    report = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "kicad_cli": cli,
        "pcbnew_available": board_metrics.pcbnew_available(),
        "projects": [
            audit_board("bms", BMS_PCB, output_dir, cli),
            audit_board("charger", CHG_PCB, output_dir, cli),
        ],
    }

    target = output_dir / "pcb_audit.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("PCB 审计：")
    for project in report["projects"]:
        print(f"  {project['project']}: {project['status']}")
    print(f"  报告: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

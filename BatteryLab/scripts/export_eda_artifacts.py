"""EDA 工程文件导出（原理图 PDF、PCB 图、Gerber、钻孔、贴片坐标、STEP）。

没有真实 PCB/原理图时逐项标记 BLOCKED，不生成替代图片，不伪造导出成功。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from eda_tools import kicad_runner

BMS_DIR = Path("hardware/eda/BatteryLab_BMS_V1")
CHG_DIR = Path("hardware/eda/BatteryLab_Charger_V1")


def _run(cli: str | None, args: list, output_dir: Path, name: str, artifact: Path, timeout: float = 300) -> dict:
    if cli is None:
        return {"artifact": str(artifact), "status": "BLOCKED_NO_KICAD"}
    if not any(Path(a).suffix == ".kicad_pcb" or Path(a).suffix == ".kicad_sch" for a in args if isinstance(a, str)):
        pass
    result = kicad_runner.run_kicad_command(cli, args, output_dir, name, timeout_s=timeout)
    return {
        "artifact": str(artifact),
        "exists": artifact.exists(),
        "size_bytes": artifact.stat().st_size if artifact.exists() else 0,
        "command_status": result.get("status"),
        "returncode": result.get("returncode"),
        "status": "EXPORTED" if artifact.exists() and artifact.stat().st_size > 0 else "FAILED_OR_EMPTY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EDA 工程文件导出")
    parser.add_argument("--cli", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else Path("results/eda") / f"run_export_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    cli = None
    try:
        cli = kicad_runner.find_kicad_cli(args.cli)
    except (FileNotFoundError, RuntimeError):
        cli = None

    sch = BMS_DIR / "BatteryLab_BMS_V1.kicad_sch"
    pcb = BMS_DIR / "BatteryLab_BMS_V1.kicad_pcb"
    gerber_dir = output_dir / "gerbers"
    drill_dir = output_dir / "drill"

    report: dict = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "kicad_cli": cli,
        "artifacts": [],
        "note": "Gerber 导出成功不等于可安全投产；本阶段未做制造评审与硬件验证",
    }

    if cli is None or not sch.is_file():
        report["artifacts"].append({"artifact": "bms_schematic.pdf", "status": "BLOCKED_NO_SCHEMATIC"})
    else:
        report["artifacts"].append(
            _run(cli, ["sch", "export", "pdf", "--output", str(output_dir / "bms_schematic.pdf"), str(sch)],
                 output_dir, "export_schematic_pdf", output_dir / "bms_schematic.pdf")
        )

    if cli is None or not pcb.is_file():
        for artifact, name in [
            ("pcb_top.svg", "svg_top"), ("pcb_bottom.svg", "svg_bottom"),
            (str(gerber_dir), "gerbers"), (str(drill_dir), "drill"),
            ("positions.csv", "pos"), ("board.step", "step"),
        ]:
            report["artifacts"].append({"artifact": artifact, "status": "BLOCKED_NO_PCB"})
    else:
        report["artifacts"].append(
            _run(cli, ["pcb", "export", "svg", "--layers", "F.Cu,F.SilkS,Edge.Cuts",
                       "--output", str(output_dir / "pcb_top"), str(pcb)],
                 output_dir, "export_svg_top", output_dir / "pcb_top.svg")
        )
        report["artifacts"].append(
            _run(cli, ["pcb", "export", "svg", "--layers", "B.Cu,B.SilkS,Edge.Cuts",
                       "--mirror", "--output", str(output_dir / "pcb_bottom"), str(pcb)],
                 output_dir, "export_svg_bottom", output_dir / "pcb_bottom.svg")
        )
        gerber_dir.mkdir(parents=True, exist_ok=True)
        drill_dir.mkdir(parents=True, exist_ok=True)
        report["artifacts"].append(
            _run(cli, ["pcb", "export", "gerbers", "--output", str(gerber_dir) + "\\", str(pcb)],
                 output_dir, "export_gerbers", gerber_dir)
        )
        report["artifacts"].append(
            _run(cli, ["pcb", "export", "drill", "--output", str(drill_dir) + "\\", str(pcb)],
                 output_dir, "export_drill", drill_dir)
        )
        report["artifacts"].append(
            _run(cli, ["pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                       "--output", str(output_dir / "positions.csv"), str(pcb)],
                 output_dir, "export_pos", output_dir / "positions.csv")
        )
        report["artifacts"].append(
            _run(cli, ["pcb", "export", "step", "--output", str(output_dir / "board.step"), str(pcb)],
                 output_dir, "export_step", output_dir / "board.step")
        )

    target = output_dir / "eda_export.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("EDA 导出：")
    for item in report["artifacts"]:
        print(f"  {item['artifact']}: {item['status']}")
    print(f"  报告: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

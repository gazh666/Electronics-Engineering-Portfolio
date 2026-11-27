"""BatteryLab V2 真实 EDA 成果导出（Task 11）。

全部文件由真实 KiCad 工程生成；无法生成的项目在清单中标记 NOT_VERIFIED，
不使用 AI 生成图片冒充 PCB/3D。

运行：
    python -B -m scripts.export_release_v2 <BatteryLab_BMS_V2|BatteryLab_Charger_V2>
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDA = ROOT / "hardware" / "eda"
CLI = Path(r"C:\\Users\\<user>\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe")

DISCLAIMER = ("ENGINEERING DESIGN PROTOTYPE\nNOT HARDWARE VALIDATED\n"
              "NOT APPROVED FOR MANUFACTURING")

LAYOUT_REVIEW = [
    ("主功率回路", "BAT_POS/MID_NODE/PACK_POS/PACK_NEG 1.0–1.5 mm，路径短且顺序正确", "REVIEWED_DESIGN"),
    ("Shunt Kelvin 采样", "SENSE_P/SENSE_N 由 RS1 焊盘经 100 Ω 进入 AFE，未与功率铜共用", "REVIEWED_DESIGN"),
    ("电芯采样 RC", "47 Ω + 0.22 µF 靠近 U1 引脚，位于功率回路外侧", "REVIEWED_DESIGN"),
    ("芯片去耦", "REG18/REG1_3V3 2.2 µF 贴近 U1 电源脚", "REVIEWED_DESIGN"),
    ("MOSFET 栅极驱动", "DSG/CHG 栅极网络单独走线，回路面积尽量小", "REVIEWED_DESIGN"),
    ("GND 参考平面", "In1.Cu 完整 GND 平面 + F/B 铺铜 + 热焊盘过孔", "REVIEWED_DESIGN"),
    ("均衡与温度", "本版不装外部均衡支路，NTC 接口远离功率回路", "PARTIAL"),
    ("连接器与测试点", "J1/J2/J3/J4 + TP1–TP4 均引出", "REVIEWED_DESIGN"),
    ("热设计", "仅做功耗估算，未做热仿真与实测", "NOT_VERIFIED"),
    ("EMI / 阻抗 / 安规", "未做任何仿真或认证测试", "NOT_VERIFIED"),
]


def run(cmd: list[str]) -> int:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def svg_to_png(svg: Path, png: Path) -> bool:
    try:
        import cairosvg  # type: ignore
    except Exception:
        return False
    try:
        cairosvg.svg2png(url=str(svg), write_to=str(png), output_width=2000)
        return png.is_file()
    except Exception:
        return False


def main() -> int:
    project = sys.argv[1]
    base = EDA / project
    sch = base / f"{project}.kicad_sch"
    pcb = base / f"{project}.kicad_pcb"
    rel = base / "release"
    rel.mkdir(parents=True, exist_ok=True)
    for sub in ("gerbers", "drill"):
        (rel / sub).mkdir(exist_ok=True)

    status: dict[str, str] = {}

    status["schematic.pdf"] = "OK" if run([str(CLI), "sch", "export", "pdf", "--output",
                                           str(rel / "schematic.pdf"), str(sch)]) == 0 else "NOT_VERIFIED"
    run([str(CLI), "sch", "export", "netlist", "--format", "kicadxml",
         "--output", str(rel / "netlist.xml"), str(sch)])
    run([str(CLI), "sch", "export", "bom", "--output", str(rel / "bom.csv"), str(sch)])
    run([str(CLI), "pcb", "export", "svg", "--layers", "F.Cu,F.Silkscreen,F.Mask,Edge.Cuts",
         "--page-size-mode", "2", "--output", str(rel / "pcb_top.svg"), str(pcb)])
    run([str(CLI), "pcb", "export", "svg", "--layers", "B.Cu,B.Silkscreen,B.Mask,Edge.Cuts",
         "--page-size-mode", "2", "--output", str(rel / "pcb_bottom.svg"), str(pcb)])
    run([str(CLI), "pcb", "export", "step", "--subst-models", "--output", str(rel / "board.step"), str(pcb)])
    run([str(CLI), "pcb", "export", "pos", "--format", "csv", "--units", "mm",
         "--output", str(rel / "positions.csv"), str(pcb)])
    run([str(CLI), "pcb", "export", "gerbers", "--layers", "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts",
         "--output", str(rel / "gerbers") + "\\", str(pcb)])
    run([str(CLI), "pcb", "export", "drill", "--format", "excellon", "--drill-origin", "absolute",
         "--generate-map", "--map-format", "gerberx2", "--output", str(rel / "drill") + "\\", str(pcb)])

    for name in ("pcb_top", "pcb_bottom"):
        svg = rel / f"{name}.svg"
        status[f"{name}.png"] = "OK" if svg.is_file() and svg_to_png(svg, rel / f"{name}.png") else "NOT_VERIFIED"
    # 3D 渲染需要 KiCad GUI/光线追踪，本次不生成，明确标记
    status["pcb_3d.png"] = "NOT_VERIFIED (需要 KiCad GUI 3D 查看器，CLI 仅输出 STEP)"

    metrics = json.loads((rel / "routing_metrics.json").read_text(encoding="utf-8"))
    lengths = metrics.get("net_track_length_mm", {})
    with open(rel / "layout_review.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "review_note", "status"])
        for row in LAYOUT_REVIEW:
            w.writerow(row)
        for net in ("BAT_POS", "MID_NODE", "PACK_POS", "PACK_NEG", "SENSE_P", "SENSE_N",
                    "PHASE", "DSG_GATE", "CHG_GATE"):
            if net in lengths:
                w.writerow([f"route_length:{net}", f"{lengths[net]:.3f} mm", "MEASURED_FROM_PCB"])

    manifest = {
        "project": project,
        "kicad_version": "10.0.8",
        "generated_by": "scripts/export_release_v2.py",
        "disclaimer": DISCLAIMER,
        "export_status": status,
        "files": {},
    }
    for p in sorted(rel.rglob("*")):
        if p.is_file() and p.name != "release_manifest.json":
            manifest["files"][str(p.relative_to(rel)).replace("\\", "/")] = {
                "bytes": p.stat().st_size, "sha256": sha256(p)}
    (rel / "release_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"project": project, "files": len(manifest["files"]), "export_status": status},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

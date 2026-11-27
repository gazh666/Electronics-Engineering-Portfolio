"""生成 EDA release 的 layout_review.csv 与 release_manifest.json（含 sha256）。

运行：
    python -B -m scripts.eda_release_manifest
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {
    "BatteryLab_BMS_V1": {
        "critical": {"U1", "Q1", "Q2", "RS1", "J1", "J2"},
        "notes": "AFE/功率/分流关键器件；SENSE_P/SENSE_N 需 Kelvin 走线，BAT_POS/PACK_POS/PACK_NEG 需 2.0mm 功率宽度",
    },
    "BatteryLab_Charger_V1": {
        "critical": {"U2", "Q3", "Q4", "L1", "RS2", "RS3", "J5"},
        "notes": "同步 Buck 功率级；PHASE 回路面积最小化，ADAPTER_P/SENSE_P 功率路径，VFB 反馈远离开关节点",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(project: str, spec: dict) -> dict:
    rel = ROOT / "hardware" / "eda" / project / "release"
    if not rel.is_dir():
        return {"project": project, "status": "NO_RELEASE"}
    # layout review
    pos = rel / "positions.csv"
    rows = []
    if pos.is_file():
        with open(pos, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                ref = r["Ref"].strip('"')
                crit = "CRITICAL" if ref in spec["critical"] else "NORMAL"
                rows.append({
                    "reference": ref,
                    "value": r["Val"].strip('"'),
                    "footprint": r["Package"].strip('"'),
                    "pos_x_mm": r["PosX"],
                    "pos_y_mm": r["PosY"],
                    "rotation_deg": r["Rot"],
                    "side": r["Side"],
                    "layout_priority": crit,
                    "review_note": spec["notes"] if crit == "CRITICAL" else "常规放置；按网表连接",
                })
        with open(rel / "layout_review.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # manifest
    files = []
    for p in sorted(rel.rglob("*")):
        if p.is_file() and p.name != "release_manifest.json":
            files.append({
                "path": str(p.relative_to(rel)).replace("\\", "/"),
                "bytes": p.stat().st_size,
                "sha256": sha256(p),
            })
    manifest = {
        "project": project,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "kicad_version": "10.0.8",
        "status": "ENGINEERING_RESEARCH_ONLY — NOT HARDWARE VALIDATED — NOT FOR PRODUCTION",
        "disclaimer": "本工程为研究性设计草稿。PCB 尚未完成实际布线（见 DRC 未连接项），未经独立硬件设计与制造评审，禁止直接投产或用于真实锂电池接线。",
        "file_count": len(files),
        "files": files,
    }
    (rel / "release_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"project": project, "files": len(files), "manifest": str(rel / "release_manifest.json")}


def main() -> int:
    out = [build(p, spec) for p, spec in PROJECTS.items()]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

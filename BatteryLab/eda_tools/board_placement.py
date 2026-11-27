"""PCB 布局应用脚本（需要本机 KiCad Python 绑定 pcbnew）。

只负责应用已经人工审核过的坐标；不保证不碰撞、不保证回流/散热/功率路径最优。
必须在真实 KiCad 中重新打开并做布局评审。
"""

from __future__ import annotations

import csv
from pathlib import Path


def pcbnew_available() -> bool:
    try:
        import pcbnew  # noqa: F401
    except Exception:
        return False
    return True


def load_approved_placement(placement_csv: str | Path) -> list[dict]:
    records = []
    with open(placement_csv, encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if str(row.get("approved", "")).lower() != "true":
                continue
            records.append(
                {
                    "reference": row["reference"],
                    "x_mm": float(row["x_mm"]),
                    "y_mm": float(row["y_mm"]),
                    "angle_deg": float(row.get("angle_deg", 0.0)),
                }
            )
    return records


def apply_reviewed_placement(
    board_path: str | Path,
    placement_csv: str | Path,
    output_path: str | Path,
) -> dict:
    import pcbnew  # 延迟导入

    source = Path(board_path)
    target = Path(output_path)

    if source.resolve() == target.resolve():
        raise ValueError("Do not overwrite source board")

    board = pcbnew.LoadBoard(str(source))
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}

    applied = []
    for record in load_approved_placement(placement_csv):
        ref = record["reference"]
        if ref not in footprints:
            raise ValueError(f"Unknown footprint: {ref}")

        footprint = footprints[ref]
        footprint.SetPosition(
            pcbnew.VECTOR2I(
                pcbnew.FromMM(record["x_mm"]),
                pcbnew.FromMM(record["y_mm"]),
            )
        )
        footprint.SetOrientationDegrees(record["angle_deg"])
        applied.append(ref)

    target.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(target), board)

    return {"applied_count": len(applied), "applied_references": applied}

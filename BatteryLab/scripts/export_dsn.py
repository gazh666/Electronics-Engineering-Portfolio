"""导出 Specctra DSN 并设置辅助布线线宽（默认 0.18 mm）。

DSN 是中间交换文件，不属于工程交付物；间距规则保持 0.20 mm 不变，仅调整走线宽度，
使 0.4 mm 间距 QFN 焊盘可逃逸。

运行：
    "<KiCad>\\bin\\python.exe" scripts/export_dsn.py <board.kicad_pcb> <out.dsn> [width_mm]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pcbnew


def main() -> int:
    board_path, dsn = Path(sys.argv[1]), Path(sys.argv[2])
    width = float(sys.argv[3]) if len(sys.argv) > 3 else 0.18
    board = pcbnew.LoadBoard(str(board_path))
    # DSN 中不导出 GND 铺铜/平面：否则 F.Cu 平面会被视为障碍，阻断辅助布线。
    # 仅内存中移除，不保存，工程文件中的铜皮保持不变。
    for z in list(board.Zones()):
        board.Remove(z)
    ok = pcbnew.ExportSpecctraDSN(board, str(dsn))
    if not ok:
        raise SystemExit("DSN export failed")
    text = dsn.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\(width\s+200\)", f"(width {int(round(width * 1000))})", text)
    dsn.write_text(text, encoding="utf-8")
    print(f"dsn={dsn} rule_width_mm={width} smd_smd_clearance_preserved=0.05")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

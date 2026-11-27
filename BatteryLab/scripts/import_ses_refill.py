"""导入 FreeRouting 的 Specctra Session（SES）并重新填充 GND 铜皮。

FreeRouting 仅作为辅助布线工具（AGPL-3.0，本地运行，不随作品集分发）。
导入后仍以 kicad-cli 真实 DRC 判定连接性与间距，不依据工具自报结果。

运行：
    "<KiCad>\\bin\\python.exe" scripts/import_ses_refill.py <board.kicad_pcb> <session.ses>
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew


def find_net(board, name):
    for i in range(board.GetNetInfo().GetNetCount()):
        ni = board.GetNetInfo().GetNetItem(i)
        if ni.GetNetname() == name:
            return ni
    return None


def add_thermal_vias(board, refs=("U1", "U2")):
    gnd = find_net(board, "GND")
    if gnd is None:
        return 0
    added = 0
    for fp in board.GetFootprints():
        if fp.GetReference() not in refs:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() != "PAD":
                continue
            c = pad.GetPosition()
            for dx, dy in ((-0.6, -0.6), (0.6, -0.6), (-0.6, 0.6), (0.6, 0.6)):
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(c.x + pcbnew.FromMM(dx), c.y + pcbnew.FromMM(dy)))
                v.SetWidth(pcbnew.FromMM(0.6))
                v.SetDrill(pcbnew.FromMM(0.3))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(gnd)
                board.Add(v)
                added += 1
    return added


def refill(board):
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def main() -> int:
    pcb, ses = Path(sys.argv[1]), Path(sys.argv[2])
    board = pcbnew.LoadBoard(str(pcb))
    ok = pcbnew.ImportSpecctraSES(board, str(ses))
    print("import ses:", ok)
    print("thermal vias:", add_thermal_vias(board))
    refill(board)
    pcbnew.SaveBoard(str(pcb), board)
    print("saved", pcb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

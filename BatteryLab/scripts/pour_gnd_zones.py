"""为 BatteryLab PCB 填充 GND 铜皮（F.Cu / B.Cu）并保存。

用 KiCad 自带 python 运行：
    "<KiCad>\\bin\\python.exe" scripts/pour_gnd_zones.py <pcb> [gnd_net]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew


def find_net(board, name):
    for fn in ("FindNet", "GetNet"):
        f = getattr(board, fn, None)
        if f:
            try:
                n = f(name)
                if n is not None:
                    return n
            except Exception:
                pass
    ni = board.GetNetInfo()
    for method in ("GetNetItem", "GetNet"):
        f = getattr(ni, method, None)
        if f:
            try:
                n = f(name)
                if n is not None:
                    return n
            except Exception:
                pass
    return None


def main() -> int:
    pcb_path = Path(sys.argv[1])
    gnd_name = sys.argv[2] if len(sys.argv) > 2 else "GND"
    board = pcbnew.LoadBoard(str(pcb_path))
    gnd = find_net(board, gnd_name)
    if gnd is None:
        print(f"NO NET {gnd_name}; skip")
        return 2
    bb = board.GetBoardEdgesBoundingBox()
    inset = pcbnew.FromMM(0.5)
    xs = [bb.GetLeft() + inset, bb.GetRight() - inset]
    ys = [bb.GetTop() + inset, bb.GetBottom() - inset]
    added = 0
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetLocalClearance(pcbnew.FromMM(0.25))
        z.SetMinThickness(pcbnew.FromMM(0.25))
        try:
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        except Exception:
            pass
        try:
            z.SetIsRuleArea(False)
        except Exception:
            pass
        o = z.Outline()
        o.NewOutline()
        for (x, y) in [(xs[0], ys[1]), (xs[1], ys[1]), (xs[1], ys[0]), (xs[0], ys[0])]:
            o.Append(pcbnew.VECTOR2I(int(x), int(y)))
        board.Add(z)
        added += 1
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"poured {added} GND zones on {pcb_path.name}; zones={len(board.Zones())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

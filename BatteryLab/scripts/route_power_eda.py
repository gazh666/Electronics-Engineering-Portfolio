"""BatteryLab V2 主功率通路手工布线（真实 PCB_TRACK 对象）。

只布主功率网络；其余网络交给 FreeRouting（DSN/SES），
功率路径宽度按 trace_width_calculation.csv 取 1.5 mm。

运行：
    "<KiCad>\\bin\\python.exe" scripts/route_power_eda.py <board.kicad_pcb> <BMS|CHG>
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

ROUTES = {
    "BMS": {
        "BAT_POS": (1.0, [("J1", "4"), ("Q1", "5")]),
        "MID_NODE": (1.0, [("Q1", "1"), ("Q2", "5")]),
        "PACK_POS": (1.0, [("Q2", "1"), (44.0, 20.98), (44.0, 13.0), ("J2", "1")]),
        "PACK_NEG": (1.5, [("J2", "2"), ("RS1", "2")]),
    },
    "CHG": {
        "INPUT_RAW": (1.5, [("J5", "1"), (13.0, 14.0), (13.0, 16.0), ("RS3", "1")]),
        "ADAPTER_P": (1.0, [("RS3", "2"), (27.0, 16.0), (27.0, 19.02), ("Q3", "5")]),
        "PHASE": (1.0, [("Q3", "1"), ("Q4", "5"), (39.45, 23.8), (46.0, 23.8), (46.0, 20.0), ("L1", "1")]),
        "SENSE_P": (1.5, [("L1", "2"), ("RS2", "1")]),
        "SENSE_N": (1.5, [("RS2", "2"), (66.0, 20.0), (66.0, 11.0), (72.0, 11.0), ("J6", "1")]),
    },
}


def pad_pos(board, ref: str, pin: str):
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == pin:
                return pad.GetPosition()
    raise SystemExit(f"pad not found {ref}.{pin}")


def main() -> int:
    pcb, which = Path(sys.argv[1]), sys.argv[2].upper()
    board = pcbnew.LoadBoard(str(pcb))
    netmap = {board.GetNetInfo().GetNetItem(i).GetNetname(): board.GetNetInfo().GetNetItem(i)
              for i in range(board.GetNetInfo().GetNetCount())}
    added = {}
    for netname, (width, pts) in ROUTES[which].items():
        net = netmap.get(netname)
        if net is None:
            print("skip missing net", netname)
            continue
        coords = []
        for p in pts:
            if isinstance(p, tuple) and len(p) == 2 and isinstance(p[0], str):
                coords.append(pad_pos(board, p[0], p[1]))
            else:
                coords.append(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])))
        n = 0
        for a, b in zip(coords, coords[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(a)
            t.SetEnd(b)
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(net)
            board.Add(t)
            n += 1
        added[netname] = n
    pcbnew.SaveBoard(str(pcb), board)
    print("power tracks:", added)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

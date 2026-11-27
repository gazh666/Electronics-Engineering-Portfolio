"""BatteryLab V2 功能分区布局 + 4 层板构建（真实 pcbnew 对象，非网格摆放）。

- 从 kicad-cli 导出的 kicadxml 网表读取器件与引脚→网络；
- 按功能分区显式放置器件（功率级 / 采样 / AFE / 接口 / 测试点）；
- In1.Cu 为完整 GND 平面，F.Cu / B.Cu 后续铺 GND；
- 本脚本只放置器件与板框，不添加信号走线（走线由 route 脚本与 FreeRouting 完成）。

运行：
    "<KiCad>\\bin\\python.exe" scripts/layout_eda_pcb_v2.py <netlist.xml> <out.kicad_pcb> <BMS|CHG>
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

FP_ROOT = Path(r"C:\\Users\\<user>\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints")

BOARD_W = 100.0
BOARD_H = 72.0

# ref: (x_mm, y_mm, rotation_deg)
LAYOUT_BMS = {
    # 主功率通路：J1 电芯 -> Q1 -> Q2 -> J2 组端 -> RS1 分流 -> GND
    "J1": (9.0, 12.0, 0),
    "Q1": (25.0, 20.0, 180),
    "Q2": (39.0, 20.0, 180),
    "J2": (50.0, 13.0, 90),
    "RS1": (58.0, 13.0, 180),
    "TP1": (66.0, 13.0, 0),
    "TP2": (66.0, 21.0, 0),
    # 电芯采样 RC
    "R101": (17.0, 30.0, 0),
    "R102": (17.0, 36.0, 0),
    "R103": (17.0, 42.0, 0),
    "R104": (17.0, 48.0, 0),
    "R105": (17.0, 54.0, 0),
    "C101": (25.0, 30.0, 0),
    "C102": (25.0, 36.0, 0),
    "C103": (25.0, 48.0, 0),
    "R106": (25.0, 42.0, 0),
    "R107": (25.0, 54.0, 0),
    # AFE
    "U1": (38.0, 36.0, 0),
    "R108": (31.0, 26.0, 0),
    "C104": (32.0, 44.0, 0),
    "C105": (38.0, 44.0, 0),
    "R112": (44.0, 44.0, 0),
    "R113": (48.0, 30.0, 0),
    "R114": (48.0, 42.0, 0),
    "R109": (58.0, 28.0, 0),
    "R110": (58.0, 34.0, 0),
    # 接口与测试点
    "J3": (84.0, 34.0, 0),
    "J4": (84.0, 50.0, 0),
    "TP3": (76.0, 48.0, 0),
    "TP4": (76.0, 54.0, 0),
}

LAYOUT_CHG = {
    # 输入 -> 输入采样 -> 半桥 -> 电感 -> 输出采样 -> 电池
    "J5": (9.0, 14.0, 0),
    "RS3": (20.0, 16.0, 0),
    "C207": (26.0, 10.0, 0),
    "Q3": (33.0, 20.0, 180),
    "Q4": (41.0, 20.0, 180),
    "L1": (51.0, 20.0, 0),
    "RS2": (60.0, 20.0, 0),
    "J6": (72.0, 15.0, 270),
    "C205": (66.0, 26.0, 0),
    "C206": (72.0, 26.0, 0),
    # 控制
    "U2": (38.0, 46.0, 0),
    "R201": (26.0, 38.0, 0),
    "R202": (32.0, 38.0, 0),
    "R203": (22.0, 46.0, 0),
    "R204": (28.0, 46.0, 0),
    "R205": (22.0, 52.0, 0),
    "R206": (28.0, 52.0, 0),
    "R207": (46.0, 38.0, 0),
    "R208": (52.0, 38.0, 0),
    "R209": (46.0, 58.0, 0),
    "R210": (52.0, 58.0, 0),
    "C201": (56.0, 46.0, 0),
    "C202": (62.0, 46.0, 0),
    "C203": (68.0, 46.0, 0),
    "C204": (56.0, 40.0, 0),
    "D1": (62.0, 40.0, 180),
    "TP5": (78.0, 58.0, 0),
    "TP6": (84.0, 58.0, 0),
    "TP7": (90.0, 58.0, 0),
}

MOUNTING_HOLES = [(5.0, 5.0), (95.0, 5.0), (5.0, 67.0), (95.0, 67.0)]


def parse_netlist(path: Path):
    root = ET.parse(path).getroot()
    comps = []
    for c in root.find("components").findall("comp"):
        comps.append({
            "ref": c.attrib["ref"],
            "value": c.findtext("value") or "",
            "footprint": c.findtext("footprint") or "",
            "datasheet": c.findtext("datasheet") or "",
        })
    pin_to_net: dict[tuple[str, str], str] = {}
    for n in root.find("nets").findall("net"):
        name = n.attrib["name"]
        for node in n.findall("node"):
            pin_to_net[(node.attrib["ref"], node.attrib["pin"])] = name
    return comps, pin_to_net


def add_edge(board, x1, y1, x2, y2):
    seg = pcbnew.PCB_SHAPE(board)
    seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    seg.SetLayer(pcbnew.Edge_Cuts)
    seg.SetWidth(pcbnew.FromMM(0.1))
    board.Add(seg)


def add_gnd_zone(board, gnd, layer, inset=0.3, clearance=0.25):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(gnd)
    zone.SetLocalClearance(pcbnew.FromMM(clearance))
    zone.SetMinThickness(pcbnew.FromMM(0.25))
    try:
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    except Exception:
        pass
    outline = zone.Outline()
    outline.NewOutline()
    for (x, y) in [(inset, inset), (BOARD_W - inset, inset),
                   (BOARD_W - inset, BOARD_H - inset), (inset, BOARD_H - inset)]:
        outline.Append(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    board.Add(zone)


def main() -> int:
    netlist, out, which = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].upper()
    layout = LAYOUT_BMS if which == "BMS" else LAYOUT_CHG

    comps, pin_to_net = parse_netlist(netlist)

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    nets: dict[str, pcbnew.NETINFO_ITEM] = {}

    def get_net(name: str):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            nets[name] = ni
        return nets[name]

    missing = []
    placed = 0
    for comp in comps:
        ref = comp["ref"]
        if ref not in layout:
            missing.append(ref)
            continue
        lib, fpname = comp["footprint"].split(":", 1)
        fp = pcbnew.FootprintLoad(str(FP_ROOT / f"{lib}.pretty"), fpname)
        if fp is None:
            raise SystemExit(f"footprint missing: {comp['footprint']} ({ref})")
        fp.SetReference(ref)
        fp.SetValue(comp["value"])
        fp.SetFPID(pcbnew.LIB_ID(lib, fpname))
        x, y, rot = layout[ref]
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        fp.SetOrientationDegrees(rot)
        # QFN 热焊盘编号与原理图一致（'PAD'）
        ep = {"U1": "33", "U2": "25"}.get(ref)
        if ep:
            for pad in fp.Pads():
                if pad.GetNumber() == ep:
                    pad.SetNumber("PAD")
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue
            net = pin_to_net.get((ref, num))
            if net is None:
                continue
            pad.SetNet(get_net(net))
        board.Add(fp)
        placed += 1

    for (x, y) in MOUNTING_HOLES:
        fp = pcbnew.FootprintLoad(str(FP_ROOT / "MountingHole.pretty"), "MountingHole_3.2mm_M3")
        if fp is None:
            continue
        fp.SetReference(f"H{MOUNTING_HOLES.index((x, y)) + 1}")
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        board.Add(fp)

    add_edge(board, 0, 0, BOARD_W, 0)
    add_edge(board, BOARD_W, 0, BOARD_W, BOARD_H)
    add_edge(board, BOARD_W, BOARD_H, 0, BOARD_H)
    add_edge(board, 0, BOARD_H, 0, 0)

    # GND：In1.Cu 完整平面 + F.Cu/B.Cu 铺铜
    gnd = get_net("GND")
    add_gnd_zone(board, gnd, pcbnew.In1_Cu)
    add_gnd_zone(board, gnd, pcbnew.F_Cu)
    add_gnd_zone(board, gnd, pcbnew.B_Cu)

    # 最小线宽 0.15 mm（6 mil，常规板厂能力），仅用于 0.4 mm 间距 QFN 逃逸；
    # 默认间距 0.20 mm 保持不变
    try:
        board.GetDesignSettings().m_TrackMinWidth = pcbnew.FromMM(0.15)
    except Exception as exc:  # pragma: no cover
        print("min track width not set:", exc)

    out.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(out), board)
    print(f"placed={placed}/{len(comps)} missing_in_layout={missing} nets={len(nets)} "
          f"board={BOARD_W}x{BOARD_H}mm layers=4 saved={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

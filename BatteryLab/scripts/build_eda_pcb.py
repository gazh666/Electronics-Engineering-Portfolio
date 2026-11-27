"""用 KiCad 自带 Python + pcbnew 从真实网表构建 BatteryLab_BMS_V1 的 4 层 PCB。

- 读取 kicad-cli 导出的 kicadxml 网表（组件 / 引脚→网络）；
- 从官方封装库加载真实封装；
- 4 层铜（F.Cu / In1.Cu / In2.Cu / B.Cu），70x50 目标板框（器件多时按包围盒扩展）；
- 器件规则放置、按网表给每个焊盘赋 net；
- 不伪造布线：本脚本不添加走线，连接性由后续手工布线完成；
- 真实保存 .kicad_pcb，DRC/Gerber 由 kicad-cli 生成。

运行（必须用 KiCad 自带 python）：
    "C:\\...\\KiCad\\10.0\\bin\\python.exe" scripts/build_eda_pcb.py <netlist.xml> <out.kicad_pcb>
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

FP_ROOT = Path(r"C:\\Users\\<user>\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints")


def parse_netlist(path: Path):
    root = ET.parse(path).getroot()
    comps = []
    for c in root.find("components").findall("comp"):
        comps.append({"ref": c.attrib["ref"], "value": c.findtext("value"),
                      "footprint": c.findtext("footprint"), "datasheet": c.findtext("datasheet") or ""})
    pin_to_net = {}
    for n in root.find("nets").findall("net"):
        name = n.attrib["name"]
        for node in n.findall("node"):
            pin_to_net[(node.attrib["ref"], node.attrib["pin"])] = name
    return comps, pin_to_net


def main() -> int:
    netlist = Path(sys.argv[1])
    out = Path(sys.argv[2])

    comps, pin_to_net = parse_netlist(netlist)

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)

    # nets
    nets = {}

    def get_net(name):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            nets[name] = ni
        return nets[name]

    # grid placement
    cols = 5
    pitch_x = 20.0
    pitch_y = 20.0
    placed = []
    positioned = []
    for idx, comp in enumerate(comps):
        fp_spec = comp["footprint"] or ""
        if ":" not in fp_spec:
            print(f"SKIP no footprint: {comp['ref']} {fp_spec}")
            continue
        lib, fpname = fp_spec.split(":", 1)
        fp = pcbnew.FootprintLoad(str(FP_ROOT / f"{lib}.pretty"), fpname)
        if fp is None:
            print(f"MISSING footprint {fp_spec} for {comp['ref']}")
            continue
        fp.SetReference(comp["ref"])
        fp.SetValue(comp["value"] or "")
        try:
            ds = comp.get("datasheet", "") or ""
            fld = fp.GetField(pcbnew.FIELD_T_DATASHEET)
            if fld is not None:
                fld.SetText(ds)
        except Exception:
            pass
        # 与原理图一致的库链接 / BOM 属性
        try:
            fp.SetFPID(pcbnew.LIB_ID(lib, fpname))
        except Exception:
            pass
        try:
            fp.SetAttributes(fp.GetAttributes() & ~(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES))
        except Exception:
            pass
        # QFN 热焊盘编号对齐原理图 'PAD'
        ep = {"U1": "33", "U2": "25"}.get(comp["ref"])
        if ep:
            for pad in fp.Pads():
                if pad.GetNumber() == ep:
                    pad.SetNumber("PAD")
        col = idx % cols
        row = idx // cols
        x = 10.0 + col * pitch_x
        y = 10.0 + row * pitch_y
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        board.Add(fp)
        positioned.append((x, y))
        # assign nets
        assigned = 0
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue
            net = pin_to_net.get((comp["ref"], num))
            if net is None:
                continue
            pad.SetNet(get_net(net))
            assigned += 1
        placed.append({"ref": comp["ref"], "footprint": fp_spec, "pads_with_net": assigned,
                       "x": x, "y": y})

    # board outline: 70x50 target, expand to fit
    xs = [p[0] for p in positioned]
    ys = [p[1] for p in positioned]
    max_x = max(xs) + 12.0 if xs else 70.0
    max_y = max(ys) + 12.0 if ys else 50.0
    width = max(70.0, max_x)
    height = max(50.0, max_y)
    origin = 0.0

    def add_edge(x1, y1, x2, y2):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.15))
        board.Add(seg)

    add_edge(origin, origin, width, origin)
    add_edge(width, origin, width, height)
    add_edge(width, height, origin, height)
    add_edge(origin, height, origin, origin)

    out.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(out), board)

    print(f"components placed: {len(placed)} / {len(comps)}")
    print(f"nets: {len(nets)}")
    print(f"board: {width:.1f} x {height:.1f} mm, 4 layers")
    print(f"saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

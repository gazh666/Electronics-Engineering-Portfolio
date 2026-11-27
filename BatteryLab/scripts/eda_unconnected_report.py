"""从真实 DRC 与网表生成"未完成网络清单"和"人工布线步骤"。

运行：
    python -B -m scripts.eda_unconnected_report
"""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ["BatteryLab_BMS_V1", "BatteryLab_Charger_V1"]
NET_RE = re.compile(r"\[([^\]]+)\]")


def pads_by_net(netlist: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    root = ET.parse(netlist).getroot()
    for n in root.find("nets").findall("net"):
        name = n.attrib["name"]
        for node in n.findall("node"):
            out[name].append(f"{node.attrib['ref']}.{node.attrib['pin']}")
    return dict(out)


def main() -> int:
    summary = {}
    for proj in PROJECTS:
        rel = ROOT / "hardware" / "eda" / proj / "release"
        drc = json.loads((rel / "drc.json").read_text(encoding="utf-8"))
        pbn = pads_by_net(rel / "netlist.xml")
        unrouted: dict[str, int] = defaultdict(int)
        for item in drc.get("unconnected_items", []):
            nets = set()
            for it in item.get("items", []):
                m = NET_RE.search(it.get("description", ""))
                if m:
                    nets.add(m.group(1))
            for nm in nets:
                unrouted[nm] += 1
        rows = []
        for nm in sorted(unrouted, key=lambda k: (-unrouted[k], k)):
            rows.append({"net": nm, "unconnected_links": unrouted[nm],
                         "pads": " ".join(pbn.get(nm, []))})
        with open(rel / "unconnected_nets.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["net", "unconnected_links", "pads"])
            w.writeheader()
            w.writerows(rows)

        md = [
            f"# {proj} 人工布线操作步骤（PCB 未完成布线）",
            "",
            f"- 未连接网络：**{len(rows)}** 个；未连接连接点合计 **{sum(unrouted.values())}**。",
            "- 状态：**PARTIAL_COMPLETION**。GND 已在 F.Cu/B.Cu 铺铜，其余网络需人工布线。",
            "",
            "## 布线前",
            "1. 在 KiCad 10 打开 `" + proj + ".kicad_pcb`。",
            "2. 确认四层叠层：F.Cu / In1.Cu / In2.Cu / B.Cu。",
            "3. 按 `hardware/eda/requirements/critical_net_rules.csv` 建立网络类与线宽（功率 2.0mm、Kelvin 0.25mm、栅极 0.4mm）。",
            "4. 为 U1/U2 的 QFN 焊盘建立 0.15mm 细间距规则（解决 4 个默认 0.2mm 间距项）。",
            "",
            "## 布线重点",
            "- 功率路径（BAT_POS / PACK_POS / PACK_NEG、PHASE）优先、短、宽，4 层并联铜皮。",
            "- SENSE_P / SENSE_N 从分流电阻焊盘内侧 Kelvin 引出，等长并行、远离功率回路。",
            "- 栅极驱动回路面积最小化，靠近 DSG/CHG/HIDRV/LODRV 引脚。",
            "- 采集 RC（47Ω/0.22µF）靠近 U1 引脚；去耦电容贴近电源脚。",
            "- 其余 GND 通过 F.Cu/B.Cu 铺铜与缝合过孔连回 In1.Cu 地平面。",
            "",
            "## 未完成网络清单（依据真实 DRC）",
            "",
            "| 网络 | 未连接连接点 | 该网焊盘 |",
            "|---|---|---|",
        ]
        for r in rows:
            md.append(f"| {r['net']} | {r['unconnected_links']} | {r['pads']} |")
        md += ["", "## 布线后", "1. 重新执行 `kicad-cli pcb drc --format json --severity-all --schematic-parity`。",
               "2. 目标：未连接=0、未解释 DRC 错误=0、一致性=0。",
               "3. 通过后重新导出 Gerber/钻孔/STEP，并更新 release_manifest.json。", ""]
        (rel / "manual_routing_steps.md").write_text("\n".join(md), encoding="utf-8")

        summary[proj] = {"unrouted_nets": len(rows), "unconnected_links": sum(unrouted.values())}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""BatteryLab V2 最终 EDA 验收：真实 ERC / DRC / 连接性 / 引脚审计 / 布线统计。

- ERC / DRC 由 kicad-cli 实际执行（--severity-all --schematic-parity）；
- 连接性只采信 DRC 的 unconnected_items，不采信布线工具自报；
- 引脚审计对比 requirements/*_pin_mapping.csv 与 kicad 导出的真实网表；
- 输出 routing_metrics.json / pin_mapping_audit.csv / unconnected_nets.csv。

运行：
    python -B -m scripts.verify_final_pcb <BatteryLab_BMS_V2|BatteryLab_Charger_V2>
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDA = ROOT / "hardware" / "eda"
KICAD_CLI = Path(r"C:\\Users\\<user>\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe")

sys.path.insert(0, str(ROOT))
from eda_tools.board_routing_audit import inspect_board  # noqa: E402


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def counts(drc: dict) -> dict:
    by_sev = defaultdict(int)
    by_type = defaultdict(int)
    for v in drc.get("violations", []):
        by_sev[v.get("severity")] += 1
        by_type[f"{v.get('severity')}:{v.get('type')}"] += 1
    return {"by_severity": dict(by_sev), "by_type": dict(by_type),
            "unconnected_items": len(drc.get("unconnected_items", [])),
            "schematic_parity": len(drc.get("schematic_parity", []))}


def erc_counts(erc: dict) -> dict:
    by_sev = defaultdict(int)
    by_type = defaultdict(int)
    for sheet in erc.get("sheets", []):
        for v in sheet.get("violations", []):
            by_sev[v.get("severity")] += 1
            by_type[f"{v.get('severity')}:{v.get('type')}"] += 1
    return {"total": sum(by_sev.values()), "by_severity": dict(by_sev), "by_type": dict(by_type)}


def pin_audit(project: str, netlist: Path, release: Path) -> list[dict]:
    mp = EDA / "requirements" / ("bms_pin_mapping.csv" if "BMS" in project else "charger_pin_mapping.csv")
    rows = list(csv.DictReader(open(mp, encoding="utf-8-sig")))
    root = ET.parse(netlist).getroot()
    pin_net = {}
    for n in root.find("nets").findall("net"):
        for node in n.findall("node"):
            pin_net[(node.attrib["ref"], node.attrib["pin"])] = n.attrib["name"]
    out = []
    for r in rows:
        ref, pin = r["reference"], r["pin_number"]
        expected = r["expected_net"].strip()
        rule = r["connection_rule"].strip()
        actual = pin_net.get((ref, pin), "")
        if rule == "ALLOWED_UNCONNECTED":
            status = "OK_UNCONNECTED" if not actual or actual.startswith("unconnected") else "UNEXPECTED_NET"
        else:
            status = "MATCH" if actual == expected else "MISMATCH"
        out.append({"reference": ref, "pin": pin, "pin_name": r["pin_name"], "rule": rule,
                    "expected_net": expected, "actual_net": actual, "status": status,
                    "datasheet": r["source_document"], "page": r["source_page"]})
    return out


def main() -> int:
    project = sys.argv[1]
    base = EDA / project
    sch = base / f"{project}.kicad_sch"
    pcb = base / f"{project}.kicad_pcb"
    release = base / "release"
    release.mkdir(parents=True, exist_ok=True)

    erc_json = release / "erc.json"
    drc_json = release / "drc.json"
    netlist = release / "netlist.xml"

    run([str(KICAD_CLI), "sch", "erc", "--format", "json", "--severity-all",
         "--output", str(erc_json), str(sch)])
    run([str(KICAD_CLI), "sch", "export", "netlist", "--format", "kicadxml",
         "--output", str(netlist), str(sch)])
    run([str(KICAD_CLI), "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity",
         "--output", str(drc_json), str(pcb)])

    erc = json.loads(erc_json.read_text(encoding="utf-8", errors="replace"))
    drc = json.loads(drc_json.read_text(encoding="utf-8", errors="replace"))
    ec, dc = erc_counts(erc), counts(drc)

    pads = defaultdict(list)
    for n in ET.parse(netlist).getroot().find("nets").findall("net"):
        for node in n.findall("node"):
            pads[n.attrib["name"]].append(f"{node.attrib['ref']}.{node.attrib['pin']}")
    unrouted = defaultdict(int)
    import re
    net_re = re.compile(r"\[([^\]]+)\]")
    for item in drc.get("unconnected_items", []):
        found = set()
        for it in item.get("items", []):
            m = net_re.search(it.get("description", ""))
            if m:
                found.add(m.group(1))
        for nm in found:
            unrouted[nm] += 1

    with open(release / "unconnected_nets.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["net", "unconnected_links", "pads"])
        w.writeheader()
        for nm in sorted(unrouted, key=lambda k: (-unrouted[k], k)):
            w.writerow({"net": nm, "unconnected_links": unrouted[nm], "pads": " ".join(pads.get(nm, []))})

    audit = pin_audit(project, netlist, release)
    with open(release / "pin_mapping_audit.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(audit[0].keys()))
        w.writeheader()
        w.writerows(audit)

    metrics = inspect_board(pcb)
    metrics.update({
        "project": project,
        "erc": ec,
        "drc": dc,
        "unconnected_net_count": len(unrouted),
        "pin_audit": {
            "total": len(audit),
            "match": sum(a["status"] == "MATCH" for a in audit),
            "ok_unconnected": sum(a["status"] == "OK_UNCONNECTED" for a in audit),
            "mismatch": sum(a["status"] in ("MISMATCH", "UNEXPECTED_NET") for a in audit),
        },
        "disclaimer": "ENGINEERING DESIGN PROTOTYPE / NOT HARDWARE VALIDATED / NOT APPROVED FOR MANUFACTURING",
    })
    (release / "routing_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("project", "footprint_count", "copper_layer_count",
                                              "track_segment_count", "via_count", "total_track_length_mm",
                                              "board_width_mm", "board_height_mm", "unconnected_net_count",
                                              "erc", "drc", "pin_audit")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

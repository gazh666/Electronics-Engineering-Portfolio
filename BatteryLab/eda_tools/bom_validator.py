"""BOM 规范化与审计。

假设输入 BOM 已经展开为"每个参考编号一行"。KiCad 分组 BOM 需要先展开，
否则同一行可能含多个参考编号，本模块会将其判为非法。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

PLACEHOLDER_VALUES = {"", "TBD", "N/A"}


def validate_bom_rows(rows: list[dict]) -> list[dict]:
    issues = []
    seen = set()

    for row in rows:
        ref = str(row.get("reference", "")).strip()
        if not ref:
            issues.append({"reference": ref, "reason": "MISSING_REFERENCE"})
            continue

        if re.search(r"[,;\s]", ref):
            issues.append({"reference": ref, "reason": "REFERENCE_NOT_EXPANDED"})
            continue

        if ref in seen:
            issues.append({"reference": ref, "reason": "DUPLICATE_REFERENCE"})
        seen.add(ref)

        dnp = str(row.get("dnp", "")).lower() in {"true", "1", "yes"}
        if dnp:
            continue

        if not row.get("footprint"):
            issues.append({"reference": ref, "reason": "MISSING_FOOTPRINT"})

        critical = str(row.get("critical", "")).lower() == "true"
        if critical:
            for field in ["manufacturer", "mpn", "datasheet_url"]:
                value = str(row.get(field, "")).strip()
                if value in PLACEHOLDER_VALUES:
                    issues.append({"reference": ref, "reason": f"MISSING_{field.upper()}"})

    return issues


def load_bom_csv(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def cross_check_bom_with_netlist(bom_rows: list[dict], netlist: dict) -> dict:
    """BOM 与网表器件集合必须一致（允许 DNP 仅在 BOM 中出现）。"""
    bom_refs = {str(r.get("reference", "")).strip() for r in bom_rows if r.get("reference")}
    net_refs = set(netlist.get("components", {}).keys())

    return {
        "in_bom_not_in_netlist": sorted(bom_refs - net_refs),
        "in_netlist_not_in_bom": sorted(net_refs - bom_refs),
        "consistent": bom_refs == net_refs,
    }

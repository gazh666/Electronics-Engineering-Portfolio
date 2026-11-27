"""关键引脚/网络自动审计。

规则（与 CSV connection_rule 列对应）：
- EXACT_NET     : 网表中该引脚必须落在 expected_net
- PRESENT       : 该引脚必须存在于任何网络中（不允许悬空），网络名不限制
- SAME_NET_AS   : 该引脚必须与 expected_net 列给出的 "REF.PIN" 处于同一网络
- DONTCARE_NET  : 允许连接任意网络（例如多功能复用引脚），但必须有记录

verified != true 的行一律 NOT_VERIFIED，不会自动变成 PASS。
"""

from __future__ import annotations

import csv
from pathlib import Path

SUPPORTED_RULES = {
    "EXACT_NET",
    "PRESENT",
    "SAME_NET_AS",
    "ALLOWED_UNCONNECTED",
    "DONTCARE_NET",
}


def _normalize_net(name: str | None) -> str | None:
    if name is None:
        return None
    return name.strip()


def audit_pin_mapping(netlist: dict, mapping_csv: str | Path) -> list[dict]:
    pin_to_net = netlist["pin_to_net"]
    results: list[dict] = []

    # 推导"同网络"关系：REF.PIN -> 网络名
    def net_of(token: str) -> str | None:
        token = token.strip()
        if "." not in token:
            return None
        ref, pin = token.rsplit(".", 1)
        return pin_to_net.get((ref, pin))

    with open(mapping_csv, encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            ref = row["reference"]
            pin = row["pin_number"]
            expected = _normalize_net(row.get("expected_net"))
            rule = row.get("connection_rule", "").strip()
            verified = str(row.get("verified", "")).strip().lower() == "true"

            actual = pin_to_net.get((ref, pin))

            if rule not in SUPPORTED_RULES:
                status = "MANUAL_REVIEW"
            elif not verified:
                status = "NOT_VERIFIED"
            elif rule == "EXACT_NET":
                status = "PASS" if actual == expected else "FAIL"
            elif rule == "PRESENT":
                status = "PASS" if actual is not None else "FAIL"
            elif rule == "ALLOWED_UNCONNECTED":
                # 数据手册明确允许悬空（例如 BQ76922 TS2/PCHG/PDSG）
                status = "PASS" if actual is None else "MANUAL_REVIEW"
            elif rule == "SAME_NET_AS":
                target_net = net_of(expected or "")
                if target_net is None:
                    status = "MANUAL_REVIEW"
                else:
                    status = "PASS" if actual == target_net else "FAIL"
            else:  # DONTCARE_NET
                status = "MANUAL_REVIEW"

            results.append(
                {
                    "reference": ref,
                    "pin_number": pin,
                    "pin_name": row.get("pin_name", ""),
                    "expected_net": expected,
                    "actual_net": actual,
                    "rule": rule,
                    "status": status,
                    "source_document": row.get("source_document", ""),
                    "source_page": row.get("source_page", ""),
                }
            )

    return results


def summarize_audit(results: list[dict]) -> dict:
    summary = {"PASS": 0, "FAIL": 0, "NOT_VERIFIED": 0, "MANUAL_REVIEW": 0}
    for item in results:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
    summary["total"] = len(results)
    summary["failures"] = [r for r in results if r["status"] == "FAIL"]
    return summary


def audit_mapping_completeness(
    mapping_csv: str | Path,
    expected_pin_count: int,
) -> dict:
    """检查映射表是否覆盖了某封装的全部引脚（用于 BQ76922 32 脚核查）。"""
    with open(mapping_csv, encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    pins = [row["pin_number"].strip() for row in rows]
    numeric_pins = [p for p in pins if p.isdigit()]
    missing = [str(i) for i in range(1, expected_pin_count + 1) if str(i) not in numeric_pins]
    non_numeric = [p for p in pins if not p.isdigit()]

    return {
        "rows": len(rows),
        "numeric_rows": len(numeric_pins),
        "non_numeric_rows": non_numeric,
        "expected_pin_count": expected_pin_count,
        "missing_pin_numbers": missing,
        "complete": not missing and len(numeric_pins) == expected_pin_count,
    }

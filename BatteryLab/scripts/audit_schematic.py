"""原理图与引脚映射审计。

流程：
1. 校验引脚映射表完整性（BQ76922 32 脚 + 热焊盘；BQ24610 24 脚 + 热焊盘）；
2. 若本机有 KiCad 且存在 .kicad_sch，则真实导出网表；
3. 若存在真实网表，则按映射表逐引脚审计；
4. 任一步缺失，明确输出 BLOCKED_*，绝不返回"零错误"。
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from eda_tools import kicad_runner, netlist_parser, pin_mapping_audit

BMS_SCH = Path("hardware/eda/BatteryLab_BMS_V1/BatteryLab_BMS_V1.kicad_sch")
BMS_MAP = Path("hardware/eda/requirements/bms_pin_mapping.csv")
CHG_SCH = Path("hardware/eda/BatteryLab_Charger_V1/BatteryLab_Charger_V1.kicad_sch")
CHG_MAP = Path("hardware/eda/requirements/charger_pin_mapping.csv")


def check_mapping(path: Path, pin_count: int) -> dict:
    completeness = pin_mapping_audit.audit_mapping_completeness(path, pin_count)
    with open(path, encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    unverified = [row["pin_number"] for row in rows if row.get("verified", "").lower() != "true"]
    return {
        "mapping_csv": str(path),
        **completeness,
        "unverified_pins": unverified,
        "verified_rows": len(rows) - len(unverified),
    }


def audit_one(name: str, sch_path: Path, mapping_path: Path, pin_count: int, output_dir: Path, cli: str | None) -> dict:
    report: dict = {"project": name, "schematic": str(sch_path), "mapping": str(mapping_path)}
    report["mapping_check"] = check_mapping(mapping_path, pin_count)

    if not sch_path.is_file():
        report["status"] = "BLOCKED_NO_SCHEMATIC"
        report["reason"] = "KiCad 原理图文件不存在（本机未完成 GUI 原理图编辑）"
        return report

    if cli is None:
        report["status"] = "BLOCKED_NO_KICAD"
        report["reason"] = "本机未找到 kicad-cli，无法导出真实网表"
        return report

    netlist_path = output_dir / f"{name}_netlist.xml"
    export = kicad_runner.run_kicad_command(
        cli,
        ["sch", "export", "netlist", "--format", "kicadxml", "--output", str(netlist_path), str(sch_path)],
        output_dir,
        f"{name}_export_netlist",
        timeout_s=180,
    )
    report["netlist_export"] = {
        "returncode": export.get("returncode"),
        "status": export.get("status"),
    }

    if not netlist_path.is_file():
        report["status"] = "BLOCKED_NETLIST_NOT_CREATED"
        return report

    netlist = netlist_parser.parse_kicad_xml_netlist(netlist_path)
    results = pin_mapping_audit.audit_pin_mapping(netlist, mapping_path)
    summary = pin_mapping_audit.summarize_audit(results)

    audit_csv = output_dir / f"{name}_pin_mapping_audit.csv"
    with open(audit_csv, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    report.update(
        {
            "status": "AUDITED",
            "netlist_summary": netlist_parser.summarize_netlist(netlist),
            "audit_summary": summary,
            "audit_csv": str(audit_csv),
        }
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="原理图引脚映射审计")
    parser.add_argument("--cli", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else Path("results/eda") / f"run_sch_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    cli = None
    cli_error = None
    try:
        cli = kicad_runner.find_kicad_cli(args.cli)
    except (FileNotFoundError, RuntimeError) as exc:
        cli_error = str(exc)

    report = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "kicad_cli": cli,
        "kicad_error": cli_error,
        "projects": [
            audit_one("bms", BMS_SCH, BMS_MAP, 32, output_dir, cli),
            audit_one("charger", CHG_SCH, CHG_MAP, 24, output_dir, cli),
        ],
    }

    target = output_dir / "schematic_audit.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("原理图审计：")
    for project in report["projects"]:
        check = project["mapping_check"]
        print(
            f"  {project['project']}: {project['status']} | "
            f"映射行 {check['rows']}/{check['expected_pin_count']}，"
            f"已核查 {check['verified_rows']}，缺失引脚 {check['missing_pin_numbers']}"
        )
    print(f"  报告: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

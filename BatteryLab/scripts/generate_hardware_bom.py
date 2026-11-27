"""生成工程 BOM 并执行 BOM 审计。

关键器件必须有真实厂家/型号/数据手册；通用无源件在未确定时标记 TBD。
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from eda_tools import bom_validator

FIELDS = [
    "project", "reference", "quantity", "value", "manufacturer", "mpn", "package",
    "footprint", "tolerance", "rating", "temperature_coefficient", "datasheet_url",
    "dnp", "critical", "verification_status", "note",
]

BMS_BOM = [
    # reference, value, manufacturer, mpn, package, footprint, tolerance, rating, tempco, datasheet, critical, status, note
    ("U1", "BQ76922", "Texas Instruments", "BQ76922", "RSN 32 QFN 4x4", "TI_RSN_32_4x4mm", "", "", "", "https://www.ti.com/lit/ds/symlink/bq76922.pdf", "true", "VERIFIED_DATASHEET", "3S-5S AFE，SLUSE86A"),
    ("Q1", "CSD18540Q5B", "Texas Instruments", "CSD18540Q5B", "SON 5x6", "TI_SON_5x6mm", "", "60 V", "", "https://www.ti.com/lit/ds/symlink/csd18540q5b.pdf", "true", "VERIFIED_DATASHEET", "高侧放电保护 FET"),
    ("Q2", "CSD18540Q5B", "Texas Instruments", "CSD18540Q5B", "SON 5x6", "TI_SON_5x6mm", "", "60 V", "", "https://www.ti.com/lit/ds/symlink/csd18540q5b.pdf", "true", "VERIFIED_DATASHEET", "高侧充电保护 FET"),
    ("RS1", "0.01R", "Vishay Dale", "WSL2010R0100FEA", "2010", "Resistor_SMD_2010", "1%", "0.5 W", "75 ppm/C", "https://www.vishay.com/docs/30100/wsl.pdf", "true", "VERIFIED_DATASHEET", "分流电阻，TC 偏离 BQ76922 建议"),
    ("R101", "47R", "TBD", "", "1206", "Resistor_SMD_1206", "1%", "0.25 W", "", "", "false", "TBD", "VC0 单体滤波，需 1206 承受均衡电流"),
    ("R102", "47R", "TBD", "", "1206", "Resistor_SMD_1206", "1%", "0.25 W", "", "", "false", "TBD", "VC1 单体滤波"),
    ("R103", "47R", "TBD", "", "1206", "Resistor_SMD_1206", "1%", "0.25 W", "", "", "false", "TBD", "VC2 单体滤波"),
    ("R104", "47R", "TBD", "", "1206", "Resistor_SMD_1206", "1%", "0.25 W", "", "", "false", "TBD", "VC4A 单体滤波"),
    ("R105", "47R", "TBD", "", "1206", "Resistor_SMD_1206", "1%", "0.25 W", "", "", "false", "TBD", "VC5 单体滤波"),
    ("R106", "0R", "TBD", "", "0603", "Resistor_SMD_0603", "", "", "", "", "false", "TBD", "VC3A 短接到 VC2"),
    ("R107", "0R", "TBD", "", "0603", "Resistor_SMD_0603", "", "", "", "", "false", "TBD", "VC3B 短接到 VC2"),
    ("C101", "0.22uF", "TBD", "", "0402", "C_0402", "10%", "16 V", "X7R", "", "false", "TBD", "VC0-VC1 差分"),
    ("C102", "0.22uF", "TBD", "", "0402", "C_0402", "10%", "16 V", "X7R", "", "false", "TBD", "VC1-VC2 差分"),
    ("C103", "0.22uF", "TBD", "", "0402", "C_0402", "10%", "16 V", "X7R", "", "false", "TBD", "VC4-VC5 差分"),
    ("C104", "2.2uF", "TBD", "", "0603", "C_0603", "10%", "16 V", "X7R", "", "false", "TBD", "REG18 去耦"),
    ("C105", "2.2uF", "TBD", "", "0603", "C_0603", "10%", "16 V", "X7R", "", "false", "TBD", "REG1 去耦"),
    ("R108", "100R", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "BAT 串联电阻"),
    ("R109", "2.2k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "I2C SCL 上拉"),
    ("R110", "2.2k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "I2C SDA 上拉"),
    ("R112", "10k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "NTC 上拉到 REG18"),
    ("R113", "100R", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "SRP 串联"),
    ("R114", "100R", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "SRN 串联"),
    ("J1", "4P", "TBD", "", "TBD", "Connector_4P_2.54mm", "", "", "", "", "false", "TBD", "3S 电芯线束"),
    ("J2", "2P", "TBD", "", "TBD", "Connector_2P_5.08mm", "", "", "", "", "false", "TBD", "组端输出"),
    ("J3", "4P", "TBD", "", "TBD", "Connector_4P_1.27mm", "", "", "", "", "false", "TBD", "I2C 主机接口"),
    ("J4", "2P", "TBD", "", "TBD", "Connector_2P_1.27mm", "", "", "", "", "false", "TBD", "NTC 接口"),
]

CHARGER_BOM = [
    ("U2", "BQ24610", "Texas Instruments", "BQ24610", "RGE 24 VQFN 4x4", "TI_RGE_24_4x4mm", "", "", "", "https://www.ti.com/lit/ds/symlink/bq24610.pdf", "true", "VERIFIED_DATASHEET", "同步 Buck 充电控制器，SLUS892D"),
    ("Q3", "CSD17578Q5A", "Texas Instruments", "CSD17578Q5A", "SON 5x6", "TI_SON_5x6mm", "", "30 V", "", "https://www.ti.com/lit/ds/symlink/csd17578q5a.pdf", "true", "VERIFIED_DATASHEET", "高边开关"),
    ("Q4", "CSD17581Q5A", "Texas Instruments", "CSD17581Q5A", "SON 5x6", "TI_SON_5x6mm", "", "30 V", "", "https://www.ti.com/lit/ds/symlink/csd17581q5a.pdf", "true", "VERIFIED_DATASHEET", "低边同步整流"),
    ("L1", "22uH", "Bourns", "SRN6045-220M", "6.0x6.0x4.5", "Inductor_Bourns_SRN6045", "20%", "1.9 A Isat", "", "https://www.bourns.com/docs/Product-Datasheets/SRN6045.pdf", "true", "VERIFIED_DATASHEET", "功率电感"),
    ("RS2", "0.01R", "Vishay Dale", "WSL2010R0100FEA", "2010", "Resistor_SMD_2010", "1%", "0.5 W", "75 ppm/C", "https://www.vishay.com/docs/30100/wsl.pdf", "true", "VERIFIED_DATASHEET", "充电电流检测"),
    ("RS3", "0.01R", "Vishay Dale", "WSL2010R0100FEA", "2010", "Resistor_SMD_2010", "1%", "0.5 W", "75 ppm/C", "https://www.vishay.com/docs/30100/wsl.pdf", "true", "VERIFIED_DATASHEET", "输入电流检测"),
    ("R201", "100k", "TBD", "", "0603", "Resistor_SMD_0603", "0.5%", "", "", "", "false", "TBD", "VFB 下臂"),
    ("R202", "475k", "TBD", "", "0603", "Resistor_SMD_0603", "0.5%", "", "", "", "false", "TBD", "VFB 上臂，设定 12.075 V"),
    ("R203", "154k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "ISET1 上臂"),
    ("R204", "10k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "ISET1 下臂"),
    ("R205", "316k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "ISET2 上臂"),
    ("R206", "10k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "ISET2 下臂"),
    ("R207", "100k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "ACSET 上臂"),
    ("R208", "10k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "ACSET 下臂"),
    ("R209", "430k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "TS 冷端阈值上臂"),
    ("R210", "9.31k", "TBD", "", "0603", "Resistor_SMD_0603", "1%", "", "", "", "false", "TBD", "TS 热端阈值下臂"),
    ("C201", "56nF", "TBD", "", "0603", "C_0603", "5%", "16 V", "X7R", "", "false", "TBD", "TTC 定时 5.23 h"),
    ("C202", "1uF", "TBD", "", "0603", "C_0603", "10%", "16 V", "X7R", "", "false", "TBD", "VREF 去耦"),
    ("C203", "1uF", "TBD", "", "0603", "C_0603", "10%", "16 V", "X7R", "", "false", "TBD", "REGN 去耦"),
    ("C204", "0.1uF", "TBD", "", "0402", "C_0402", "10%", "25 V", "X7R", "", "false", "TBD", "BTST 自举"),
    ("C205", "4.7uF", "TBD", "", "1206", "C_1206", "10%", "25 V", "X7R", "", "false", "TBD", "输出电容 1"),
    ("C206", "4.7uF", "TBD", "", "1206", "C_1206", "10%", "25 V", "X7R", "", "false", "TBD", "输出电容 2"),
    ("C207", "10uF", "TBD", "", "1206", "C_1206", "10%", "25 V", "X7R", "", "false", "TBD", "输入电容"),
    ("D1", "BAT54", "TBD", "", "SOT-23", "Diode_SOT-23", "", "30 V", "", "", "false", "TBD", "BTST 自举二极管"),
    ("J5", "2P", "TBD", "", "TBD", "Connector_2P_5.08mm", "", "", "", "", "false", "TBD", "适配器输入"),
]


def build_rows(project: str, table: list[tuple]) -> list[dict]:
    rows = []
    for (ref, value, mfr, mpn, package, footprint, tol, rating, tempco, url, critical, status, note) in table:
        rows.append(
            {
                "project": project,
                "reference": ref,
                "quantity": 1,
                "value": value,
                "manufacturer": mfr,
                "mpn": mpn,
                "package": package,
                "footprint": footprint,
                "tolerance": tol,
                "rating": rating,
                "temperature_coefficient": tempco,
                "datasheet_url": url,
                "dnp": "false",
                "critical": critical,
                "verification_status": status,
                "note": note,
            }
        )
    return rows


def summarize(rows: list[dict]) -> dict:
    critical = [r for r in rows if r["critical"] == "true"]
    verified = [r for r in critical if r["verification_status"] == "VERIFIED_DATASHEET"]
    return {
        "row_count": len(rows),
        "critical_count": len(critical),
        "critical_verified": len(verified),
        "critical_tbd": len(critical) - len(verified),
        "passive_tbd": len([r for r in rows if r["critical"] != "true" and r["verification_status"] == "TBD"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成并审计工程 BOM")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else Path("results/eda") / f"run_bom_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = build_rows("BatteryLab_BMS_V1", BMS_BOM) + build_rows("BatteryLab_Charger_V1", CHARGER_BOM)

    bom_path = output_dir / "bom.csv"
    with open(bom_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    issues = bom_validator.validate_bom_rows(rows)
    validation = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "bom_file": str(bom_path),
        "issue_count": len(issues),
        "issues": issues,
        "bms": summarize([r for r in rows if r["project"] == "BatteryLab_BMS_V1"]),
        "charger": summarize([r for r in rows if r["project"] == "BatteryLab_Charger_V1"]),
        "note": "通用无源件与连接器仍为 TBD，未虚构商业型号",
    }
    (output_dir / "bom_validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("BOM 生成与审计：")
    print(f"  行数: {len(rows)}；问题: {len(issues)}")
    print(f"  BMS: {validation['bms']}")
    print(f"  充电板: {validation['charger']}")
    print(f"  输出: {bom_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""第八阶段标准运行入口。

--profile smoke    : 只做环境、映射完整性与设计计算
--profile standard : 追加 BOM、审计状态、导出状态、发布清单与验收汇总

所有输出写入新的 Run ID 目录，不覆盖历史结果。
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from eda_tools import (
    bom_validator,
    kicad_runner,
    pin_mapping_audit,
    release_manifest,
)
from scripts.generate_hardware_bom import BMS_BOM, CHARGER_BOM, FIELDS, build_rows, summarize
from scripts.hardware_design_calculation import compute_design

BMS_MAP = Path("hardware/eda/requirements/bms_pin_mapping.csv")
CHG_MAP = Path("hardware/eda/requirements/charger_pin_mapping.csv")
BMS_SCH = Path("hardware/eda/BatteryLab_BMS_V1/BatteryLab_BMS_V1.kicad_sch")
BMS_PCB = Path("hardware/eda/BatteryLab_BMS_V1/BatteryLab_BMS_V1.kicad_pcb")


def new_run_dir(profile: str) -> Path:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    path = Path("results/eda") / f"run_stage8_{run_id}"
    path.mkdir(parents=True, exist_ok=False)
    (path / "profile.txt").write_text(profile, encoding="utf-8")
    (path / "run_id.txt").write_text(run_id, encoding="utf-8")
    return path


def pip_check() -> dict:
    process = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    return {
        "returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="BatteryLab 第八阶段标准运行")
    parser.add_argument("--profile", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--cli", default=None, help="显式 kicad-cli 路径")
    args = parser.parse_args()

    run_dir = new_run_dir(args.profile)
    log_lines: list[str] = []
    checks: list[dict] = []

    def log(message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        log_lines.append(line)
        print(line)

    # 1. 元数据
    kicad_cli = None
    kicad_error = None
    try:
        kicad_cli = kicad_runner.find_kicad_cli(args.cli)
    except (FileNotFoundError, RuntimeError) as exc:
        kicad_error = str(exc)

    metadata = {
        "stage": 8,
        "profile": args.profile,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "kicad_cli": kicad_cli,
        "kicad_error": kicad_error,
        "disclaimer": "Engineering Prototype Design — Not Hardware Validated",
        "projects": ["BatteryLab_BMS_V1", "BatteryLab_Charger_V1"],
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"run_dir={run_dir}")
    log(f"python={metadata['python_version']} kicad_cli={kicad_cli or 'NOT_FOUND'}")
    checks.append({"name": "python_environment", "status": "PASS", "detail": metadata["python_version"]})

    # 2. 依赖
    deps = pip_check()
    (run_dir / "pip_check.json").write_text(
        json.dumps(deps, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    dependency_status = "PASS" if deps["returncode"] == 0 else "FAIL"
    checks.append({"name": "pip_check", "status": dependency_status, "detail": deps["stdout"]})
    log(f"pip check: {dependency_status}")

    # 3. KiCad
    if kicad_cli:
        version = kicad_runner.run_kicad_command(kicad_cli, ["version"], run_dir, "kicad_version", 60)
        (run_dir / "kicad_version.txt").write_text(
            (version.get("stdout") or "").strip(), encoding="utf-8"
        )
        checks.append({"name": "kicad_available", "status": "PASS", "detail": (version.get("stdout") or "").strip()})
    else:
        (run_dir / "kicad_version.txt").write_text("KICAD_NOT_FOUND", encoding="utf-8")
        checks.append({"name": "kicad_available", "status": "BLOCKED", "detail": kicad_error})
    log(f"kicad_available: {checks[-1]['status']}")

    # 4. 引脚映射完整性
    bms_check = pin_mapping_audit.audit_mapping_completeness(BMS_MAP, 32)
    chg_check = pin_mapping_audit.audit_mapping_completeness(CHG_MAP, 24)
    mapping = {"bms": bms_check, "charger": chg_check}
    (run_dir / "pin_mapping_completeness.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    checks.append({
        "name": "bms_pin_mapping_complete",
        "status": "PASS" if bms_check["complete"] else "FAIL",
        "detail": f"rows={bms_check['rows']} missing={bms_check['missing_pin_numbers']}",
    })
    checks.append({
        "name": "charger_pin_mapping_complete",
        "status": "PASS" if chg_check["complete"] else "FAIL",
        "detail": f"rows={chg_check['rows']} missing={chg_check['missing_pin_numbers']}",
    })
    log(f"pin mapping: bms={bms_check['complete']} charger={chg_check['complete']}")

    # 5. 设计计算
    design = compute_design()
    (run_dir / "design_calculations.json").write_text(
        json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    checks.append({"name": "design_calculations", "status": "PASS", "detail": "解析计算完成"})

    summary = design["summary"]
    per_cell = summary["charge_voltage_actual_v"] / 3.0
    checks.append({
        "name": "charge_voltage_below_cell_ov",
        "status": "PASS" if per_cell < 4.25 else "FAIL",
        "detail": f"{per_cell:.4f} V/cell < 4.25 V 过压阈值",
    })
    checks.append({
        "name": "shunt_power_within_rating",
        "status": "PASS" if summary["shunt_power_at_2p5a_w"] <= 0.5 else "FAIL",
        "detail": f"{summary['shunt_power_at_2p5a_w']*1000:.1f} mW / 500 mW",
    })
    balanced_ok = summary["balancing_worst_external_power_w"] <= 0.25
    checks.append({
        "name": "balancing_resistor_power",
        "status": "PASS" if balanced_ok else "FAIL",
        "detail": f"{summary['balancing_worst_external_power_w']*1000:.1f} mW / 250 mW (1206)",
    })
    lc_ok = 12.0 <= summary["lc_resonance_khz"] <= 17.0
    checks.append({
        "name": "lc_resonance_target",
        "status": "PASS" if lc_ok else "FAIL",
        "detail": f"{summary['lc_resonance_khz']:.2f} kHz, target 12-17 kHz",
    })

    # 6. 标准档追加 BOM 与交付状态
    if args.profile == "standard":
        rows = build_rows("BatteryLab_BMS_V1", BMS_BOM) + build_rows("BatteryLab_Charger_V1", CHARGER_BOM)
        import csv as _csv

        with open(run_dir / "bom.csv", "w", encoding="utf-8-sig", newline="") as file:
            writer = _csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        issues = bom_validator.validate_bom_rows(rows)
        bom_report = {
            "issue_count": len(issues),
            "issues": issues,
            "bms": summarize([r for r in rows if r["project"] == "BatteryLab_BMS_V1"]),
            "charger": summarize([r for r in rows if r["project"] == "BatteryLab_Charger_V1"]),
        }
        (run_dir / "bom_validation.json").write_text(
            json.dumps(bom_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        checks.append({
            "name": "bom_validation",
            "status": "PASS" if not issues else "FAIL",
            "detail": f"issues={len(issues)} critical_verified={bom_report['bms']['critical_verified']+bom_report['charger']['critical_verified']}",
        })
        log(f"bom_validation: {checks[-1]['status']}")

        blocked = []
        for name, path, status in [
            ("bms_schematic", BMS_SCH, "BLOCKED_NO_KICAD_GUI"),
            ("bms_pcb", BMS_PCB, "BLOCKED_NO_KICAD_GUI"),
        ]:
            present = path.is_file()
            blocked.append({"item": name, "path": str(path), "present": present, "status": "PRESENT" if present else status})
        for name in ["erc_raw.json", "drc_raw.json", "schematic.pdf", "gerbers", "drill", "board.step"]:
            blocked.append({"item": name, "path": str(run_dir / name), "present": (run_dir / name).exists(), "status": "NOT_PRODUCED" if not (run_dir / name).exists() else "PRESENT"})
        (run_dir / "blocked_items.json").write_text(
            json.dumps(blocked, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for item in blocked:
            checks.append({
                "name": f"artifact_{item['item']}",
                "status": "PASS" if item["present"] else "BLOCKED",
                "detail": item["status"],
            })

    # 7. 汇总（先写汇总与日志，最后生成包含它们的交付清单）
    checks.append({
        "name": "release_manifest",
        "status": "PASS",
        "detail": "清单在写入汇总与日志后生成",
    })

    counts: dict[str, int] = {}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1

    validation = {
        "stage": 8,
        "profile": args.profile,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
        "status_counts": counts,
        "hardware_validated": False,
        "production_released": False,
        "note": "BLOCKED 表示需要本机 KiCad GUI 或 Administrator 权限才能继续，不属于通过",
    }
    (run_dir / "validation_summary.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log("checks: " + json.dumps(counts, ensure_ascii=False))
    (run_dir / "execution.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    # 8. 交付清单（最后生成，纳入前面的所有产物）
    log("generating release manifest")
    manifest = release_manifest.create_release_manifest(
        run_dir,
        run_dir / "release_manifest.json",
        extra_metadata={
            "run_id": (run_dir / "run_id.txt").read_text(encoding="utf-8"),
            "profile": args.profile,
            "kicad_available": bool(kicad_cli),
        },
    )
    log(f"release manifest: {manifest['file_count']} files hashed")
    (run_dir / "execution.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    print("\n阶段 8 运行完成：", run_dir)
    print("状态汇总：", counts)
    print(f"交付清单：{manifest['file_count']} 个文件已哈希")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

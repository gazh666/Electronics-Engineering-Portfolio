"""第九阶段标准运行入口。

--profile smoke    : 接口核验 + 行为级保护注入（快速）
--profile standard : 接口、真实功率映射、联合 SPICE、平均模型、保护、长期、
                     老化、能量、TestLab、三项目回归、工程图与发布清单

所有结论来自实际运行；BLOCKED / NOT_VERIFIED 原样保留。
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from battery_models.parameters import PROJECT_ROOT  # noqa: E402
from eda_tools.release_manifest import create_release_manifest  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, write_json  # noqa: E402
from validation.cross_project_regression import compare_project_snapshots, snapshot_projects  # noqa: E402


def run_step(module: str, arguments: list[str], log: list[str], timeout_s: int = 3600) -> dict:
    command = [sys.executable, "-B", "-m", module, *arguments]
    started = datetime.now()
    process = subprocess.run(
        command, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout_s,
    )
    duration = (datetime.now() - started).total_seconds()
    entry = {
        "module": module,
        "returncode": process.returncode,
        "duration_s": duration,
        "stdout_tail": (process.stdout or "")[-1500:],
        "stderr_tail": (process.stderr or "")[-1500:],
        "status": "COMMAND_OK" if process.returncode == 0 else "COMMAND_FAILED",
    }
    log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {module} -> {entry['status']} "
               f"({duration:.1f}s) rc={process.returncode}")
    return entry


def latest_power_map_available() -> bool:
    base = PROJECT_ROOT / "results" / "converter_power_map"
    return any(base.glob("*/converter_power_map_*.csv"))


def main() -> int:
    parser = argparse.ArgumentParser(description="BatteryLab 第九阶段标准运行")
    parser.add_argument("--profile", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--regenerate-power-map", action="store_true")
    parser.add_argument("--skip-figures", action="store_true")
    args = parser.parse_args()

    run_id = f"run_stage9_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    directory = STAGE9_RESULTS / run_id
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "run_id.txt").write_text(run_id, encoding="utf-8")
    log: list[str] = []
    steps: dict[str, dict] = {}

    metadata = {
        "stage": 9,
        "profile": args.profile,
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "hardware_validated": False,
        "fabricated": False,
        "assembled": False,
    }
    write_json(directory / "metadata.json", metadata)
    before_snapshot = snapshot_projects()
    write_json(directory / "source_snapshot_before.json", before_snapshot)

    baseline = run_step(
        "scripts.verify_project_interfaces",
        ["--run-dir", str(directory / "01_interfaces"),
         "--json-out", str(directory / "01_interfaces_summary.json")],
        log,
    )
    steps["01_interfaces"] = baseline

    steps["02_protection"] = run_step(
        "scripts.system_protection_demo",
        ["--run-dir", str(directory / "02_protection"),
         "--json-out", str(directory / "02_protection_summary.json")]
        + (["--spice"] if args.profile == "standard" else []),
        log,
    )

    if args.profile == "standard":
        if args.regenerate_power_map or not latest_power_map_available():
            steps["03_power_map"] = run_step(
                "scripts.generate_converter_power_map",
                ["--run-dir", str(directory / "03_power_map"),
                 "--json-out", str(directory / "03_power_map_summary.json")],
                log, timeout_s=3600,
            )
        else:
            steps["03_power_map"] = {"status": "REUSED_EXISTING_REAL_MAP",
                                     "note": "已有真实功率映射，未重复求解"}
            log.append("[power map] 复用已有真实映射 CSV")

        steps["04_integrated_spice"] = run_step(
            "scripts.integrated_buck_demo",
            ["--run-dir", str(directory / "04_integrated"),
             "--json-out", str(directory / "04_integrated_summary.json")],
            log,
        )
        steps["05_load_step"] = run_step(
            "scripts.system_load_step_demo",
            ["--run-dir", str(directory / "05_load_step"),
             "--json-out", str(directory / "05_load_step_summary.json")],
            log,
        )
        steps["06_discharge"] = run_step(
            "scripts.system_discharge_demo",
            ["--run-dir", str(directory / "06_discharge"),
             "--json-out", str(directory / "06_discharge_summary.json")],
            log,
        )
        steps["07_aging"] = run_step(
            "scripts.system_aging_demo",
            ["--run-dir", str(directory / "07_aging"),
             "--json-out", str(directory / "07_aging_summary.json")],
            log,
        )
        steps["08_energy"] = run_step(
            "scripts.system_energy_demo",
            ["--run-dir", str(directory / "08_energy"),
             "--json-out", str(directory / "08_energy_summary.json")],
            log,
        )
        steps["09_testlab"] = run_step(
            "scripts.testlab_integration_demo",
            ["--run-dir", str(directory / "09_testlab"),
             "--json-out", str(directory / "09_testlab_summary.json")],
            log,
        )
        if not args.skip_figures:
            steps["10_figures"] = run_step(
                "scripts.system_engineering_figures",
                ["--run-dir", str(directory / "10_figures"),
                 "--json-out", str(directory / "10_figures_summary.json")],
                log,
            )

    after_snapshot = snapshot_projects()
    write_json(directory / "source_snapshot_after.json", after_snapshot)
    regression = compare_project_snapshots(before_snapshot, after_snapshot)
    write_json(directory / "cross_project_regression.json", regression)

    checks: list[dict] = []
    checks.append({"name": "python_environment", "status": "PASS", "detail": metadata["python"]})
    checks.append({
        "name": "projects_available",
        "status": "PASS" if regression["read_only_projects"] else "BLOCKED",
        "detail": f"read_only={regression['read_only_projects']}",
    })
    checks.append({
        "name": "read_only_projects_unchanged",
        "status": regression["status"],
        "detail": f"modified={regression['modified_read_only_projects']}",
    })

    for name, step in steps.items():
        if step.get("status") == "REUSED_EXISTING_REAL_MAP":
            continue
        checks.append({
            "name": f"step_{name}",
            "status": "PASS" if step.get("returncode") == 0 else "FAIL",
            "detail": f"rc={step.get('returncode')} {step.get('duration_s', 0):.1f}s",
        })

    def load_summary(name: str) -> dict:
        path = directory / f"{name}_summary.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    case_statuses: dict[str, dict] = {}
    for key in ("02_protection", "04_integrated", "05_load_step", "06_discharge",
                "07_aging", "08_energy", "09_testlab"):
        payload = load_summary(key)
        if payload:
            case_statuses[key] = {
                "status": payload.get("status"),
                "case_status": payload.get("case_status"),
            }
            checks.append({
                "name": f"case_{key}",
                "status": payload.get("status") or "NOT_VERIFIED",
                "detail": payload.get("case_status") or payload.get("reason") or "未给出状态",
            })

    counts: dict[str, int] = {}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1

    validation = {
        "stage": 9,
        "profile": args.profile,
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
        "status_counts": counts,
        "steps": steps,
        "case_statuses": case_statuses,
        "cross_project_regression": regression,
        "hardware_validated": False,
        "production_released": False,
        "note": "PASS 仅表示本阶段仿真/调用/文件证据成立，不代表硬件验证或产品发布",
    }
    write_json(directory / "validation_summary.json", validation)

    (directory / "execution.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    manifest = create_release_manifest(
        directory,
        directory / "release_manifest.json",
        extra_metadata={
            "run_id": run_id,
            "profile": args.profile,
            "hardware_validated": False,
        },
    )
    print(json.dumps({
        "run_id": run_id,
        "profile": args.profile,
        "status_counts": counts,
        "manifest_files": manifest.get("file_count") if isinstance(manifest, dict) else None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

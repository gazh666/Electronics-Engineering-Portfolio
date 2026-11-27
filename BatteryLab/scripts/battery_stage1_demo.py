"""Task 30：第一阶段统一验收入口。

复用已有真实运行结果，不重复下载数据、不重复长仿真。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from storage.result_store import RESULTS_ROOT, RunDirectory, read_json, write_json

CATEGORIES = {
    "environment": ("stage1", "environment"),
    "spm": ("pybamm", "spm"),
    "thevenin": ("pybamm", "thevenin"),
    "experiment": ("pybamm", "experiment"),
    "spice": ("spice", "spice"),
    "calce": ("calce", "calce"),
}


def _latest(category: str) -> Path | None:
    folder = RESULTS_ROOT / category
    if not folder.exists():
        return None
    runs = sorted([path for path in folder.iterdir() if path.is_dir()], key=lambda path: path.name)
    return runs[-1] if runs else None


def _load(path: Path | None, name: str = "summary.json") -> dict | None:
    if path is None:
        return None
    target = path / name
    if not target.exists():
        return None
    return read_json(target)


def _find(kind: str) -> tuple[Path | None, dict | None]:
    for category in ("stage1", "pybamm", "spice", "calce"):
        folder = RESULTS_ROOT / category
        if not folder.exists():
            continue
        for run in sorted(folder.iterdir(), reverse=True):
            metadata = _load(run, "metadata.json") or {}
            script = str(metadata.get("script", ""))
            if kind == "spm" and "spm_demo" in script:
                return run, _load(run)
            if kind == "thevenin" and "thevenin_demo" in script:
                return run, _load(run)
            if kind == "experiment" and "charge_discharge" in script:
                return run, _load(run)
            if kind == "spice" and "spice_environment" in script:
                return run, _load(run)
            if kind == "calce" and "calce_data_demo" in script:
                return run, _load(run)
            if kind == "environment" and "verify_environment" in script:
                return run, _load(run)
    return None, None


def main() -> int:
    found: dict[str, dict] = {}
    checks: list[dict] = []

    for kind in ("environment", "spm", "thevenin", "experiment", "spice", "calce"):
        path, summary = _find(kind)
        found[kind] = {"run_path": str(path) if path else None, "summary": summary}
        status = "PASS" if path is not None and summary else "NOT_VERIFIED"
        checks.append({"item": kind, "status": status, "evidence": str(path) if path else None})

    environment = found["environment"]["summary"] or {}
    environment_core = environment.get("summary", environment)
    pybamm_status = environment_core.get("pybamm_backend_status", "NOT_VERIFIED")
    ngspice_status = environment_core.get("ngspice_backend_status", "NOT_VERIFIED")

    run = RunDirectory("stage1")
    validation = {
        "created_at_run": run.run_id,
        "data_source": "aggregated_real_runs",
        "checks": checks,
        "pybamm_backend_status": pybamm_status,
        "ngspice_backend_status": ngspice_status,
        "environment": environment,
        "spm": found["spm"]["summary"],
        "thevenin": found["thevenin"]["summary"],
        "experiment": found["experiment"]["summary"],
        "spice": found["spice"]["summary"],
        "calce": {
            key: value
            for key, value in (found["calce"]["summary"] or {}).items()
            if key not in {"dataset_summaries", "plots"}
        },
        "all_items_verified": all(check["status"] == "PASS" for check in checks),
    }
    run.write_metadata({"script": "scripts/battery_stage1_demo.py", "kind": "stage1_validation"})
    write_json(run.path / "environment.json", environment)
    write_json(run.path / "validation_summary.json", validation)
    if found["calce"]["summary"]:
        write_json(run.path / "dataset_summary.json", found["calce"]["summary"].get("dataset_summaries", []))
    run.log("第一阶段验收汇总完成")
    run.flush_log()

    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "run_path": str(run.path),
                "all_items_verified": validation["all_items_verified"],
                "pybamm_backend_status": pybamm_status,
                "ngspice_backend_status": ngspice_status,
                "checks": checks,
                "spm_run": found["spm"]["run_path"],
                "thevenin_run": found["thevenin"]["run_path"],
                "experiment_run": found["experiment"]["run_path"],
                "spice_run": found["spice"]["run_path"],
                "calce_run": found["calce"]["run_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if validation["all_items_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

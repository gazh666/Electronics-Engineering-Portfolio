"""Web 平台环境自检（第九阶段 Task 17）。

只做静态检查与一次真实写入探测，不运行 SPICE 仿真。

用法：
    conda run -n kaifa_power python -m scripts.verify_web
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "results" / "stage9"


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def main() -> int:
    checks: list[dict] = []
    for module_name in ("streamlit", "plotly", "pandas", "numpy", "yaml", "PySpice"):
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "unknown")
            checks.append(_check(f"import:{module_name}", True, f"version={version}"))
        except Exception as error:  # noqa: BLE001
            checks.append(_check(f"import:{module_name}", False, f"{type(error).__name__}: {error}"))

    for relative in (
        "configs/web_config.yaml",
        "configs/job_limits.yaml",
        "app.py",
        "ui/service.py",
        "jobs/manager.py",
        "storage/run_index.py",
    ):
        path = PROJECT_ROOT / relative
        checks.append(_check(f"file:{relative}", path.is_file(), str(path)))

    try:
        from jobs.registry import ALLOWED_JOB_TYPES, MODEL_SPECS

        checks.append(
            _check("registry:job_types", len(ALLOWED_JOB_TYPES) == 6, str(ALLOWED_JOB_TYPES))
        )
        checks.append(
            _check(
                "registry:models",
                set(MODEL_SPECS) == {
                    "voltage_divider",
                    "rc_transient",
                    "rl_transient",
                    "rlc_transient",
                    "buck_ideal",
                    "nonideal_buck",
                },
                str(sorted(MODEL_SPECS)),
            )
        )
    except Exception as error:  # noqa: BLE001
        checks.append(_check("registry:load", False, f"{type(error).__name__}: {error}"))

    try:
        from jobs.resource_budget import load_limits

        limits = load_limits()
        checks.append(
            _check(
                "budget:limits",
                limits.maximum_concurrent_jobs == 1,
                f"concurrency={limits.maximum_concurrent_jobs}, "
                f"max_job_s={limits.maximum_single_job_seconds}, "
                f"max_runs={limits.maximum_unique_spice_runs}",
            )
        )
    except Exception as error:  # noqa: BLE001
        checks.append(_check("budget:limits", False, f"{type(error).__name__}: {error}"))

    try:
        from storage.run_index import build_index

        index = build_index()
        checks.append(_check("index:build", True, f"runs={len(index.entries)}"))
    except Exception as error:  # noqa: BLE001
        checks.append(_check("index:build", False, f"{type(error).__name__}: {error}"))

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tmp", dir=PROJECT_ROOT / "results", delete=True
        ) as handle:
            handle.write("probe")
            handle.flush()
        checks.append(_check("results:writable", True, str(PROJECT_ROOT / "results")))
    except Exception as error:  # noqa: BLE001
        checks.append(_check("results:writable", False, f"{type(error).__name__}: {error}"))

    try:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=90)
        app.run()
        errors = [str(item.value) for item in app.exception]
        checks.append(_check("ui:home_render", not errors, "; ".join(errors) or "no exception"))
    except Exception as error:  # noqa: BLE001
        checks.append(_check("ui:home_render", False, f"{type(error).__name__}: {error}"))

    passed = sum(1 for item in checks if item["status"] == "PASS")
    overall = "PASS" if passed == len(checks) else "FAIL"
    payload = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "overall_status": overall,
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "note": "静态检查与首页渲染检查；不包含 SPICE 求解与人工视觉验收",
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / "web_verification.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in checks:
        print(f"[{item['status']}] {item['name']}: {item['detail']}")
    print(f"\n{overall} ({passed}/{len(checks)}) -> {target}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

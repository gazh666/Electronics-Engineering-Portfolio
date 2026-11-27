"""性能报告演示：把最新一次运行目录渲染为 HTML。"""

from __future__ import annotations

from pathlib import Path

from circuits.nonideal_config import load_nonideal_buck_config
from reports.performance_report import write_performance_report
from scripts.performance_common import (
    PERFORMANCE_RESULTS_ROOT,
    run_performance_case,
    save_performance_run,
)
from storage.result_store import ResultStore


def latest_run(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = [
        path
        for path in root.glob("run_*")
        if path.is_dir() and (path / "performance_metrics.json").exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main() -> int:
    root = Path(PERFORMANCE_RESULTS_ROOT)
    run_dir = latest_run(root)
    if run_dir is None:
        config = load_nonideal_buck_config()
        payload = run_performance_case(config, variant="E", include_spectrum=True)
        store = ResultStore(root=root)
        run_id, run_dir = store.create_run_dir()
        save_performance_run(
            payload,
            config,
            store,
            run_dir,
            title="Model E Performance",
            make_figures=True,
        )
        print(f"[report] generated a new run: {run_id}")

    output = write_performance_report(run_dir)
    print(f"[report] run_dir={run_dir}")
    print(f"[report] html={output} size={output.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

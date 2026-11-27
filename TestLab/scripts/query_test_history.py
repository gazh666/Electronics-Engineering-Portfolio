"""查询 SQLite 测试历史（阶段七）。

示例::

    conda run -n kaifa python -m scripts.query_test_history --list
    conda run -n kaifa python -m scripts.query_test_history --run-id <run_id>
    conda run -n kaifa python -m scripts.query_test_history --run-id <run_id> --failed-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import results_dir  # noqa: E402
from scripts.automation_context import DEFAULT_DB  # noqa: E402
from storage.sqlite_store import SQLiteStore  # noqa: E402


def _print_runs(store: SQLiteStore, limit: int) -> None:
    runs = store.list_runs()
    if not runs:
        print("数据库暂无运行记录。")
        return

    print(f"最近 {min(limit, len(runs))} 次运行（共 {len(runs)} 次）:\n")
    for run in runs[:limit]:
        summary = store.get_run_summary(run["run_id"])
        print(
            f"{run['run_id']}  {run['status']:9s}  "
            f"suite={run['suite_id'] or '-'}  计划={run['planned_count']}  "
            f"PASS={summary['PASS']} FAIL={summary['FAIL']} "
            f"ERROR={summary['ERROR']} SKIP={summary['SKIP']}"
        )
        print(f"  开始: {run['started_at']}  结束: {run['finished_at'] or '-'}")


def _print_results(store: SQLiteStore, run_id: str, failed_only: bool) -> int:
    run = store.get_run(run_id)
    if run is None:
        print(f"错误: 数据库中没有运行 {run_id}", file=sys.stderr)
        return 1

    rows = store.get_results_by_run(run_id)
    if failed_only:
        rows = [row for row in rows if row["status"] in ("FAIL", "ERROR")]

    print(f"运行 {run_id}  status={run['status']}")
    print(f"suite={run['suite_id']}  开始={run['started_at']}  结束={run['finished_at']}")
    if run["summary_json"]:
        print(f"汇总: {run['summary_json']}")
    print()

    if not rows:
        print("没有符合条件的记录。")
        return 0

    for row in rows:
        print(
            f"[{row['status']:5s}] #{row['execution_index']} "
            f"{row['case_id']} {row['case_name']} "
            f"({row['duration_ms']:.1f} ms)"
        )
        if row["error_message"]:
            print(f"  说明: {row['error_message']}")
        for check in store.get_checks(row["result_id"]):
            if check["status"] in ("FAIL", "ERROR"):
                print(
                    f"  - [{check['status']}] {check['check_name']}: "
                    f"实际 {check['actual_json']} 期望 {check['expected_json']}"
                )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="查询 TestLab 测试历史")
    parser.add_argument("--list", action="store_true", help="列出最近的运行")
    parser.add_argument("--run-id", help="查看指定运行的详细结果")
    parser.add_argument("--failed-only", action="store_true", help="只看 FAIL/ERROR")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args(argv)

    store = SQLiteStore(args.db)

    if args.run_id:
        code = _print_results(store, args.run_id, args.failed_only)
        summary_path = results_dir() / "automation" / f"run_{args.run_id}" / "summary.json"
        if summary_path.exists():
            with summary_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            print(f"\nJSONL 运行目录汇总: {json.dumps(payload['summary'], ensure_ascii=False)}")
            print(f"目录: {summary_path.parent}")
        return code

    _print_runs(store, max(1, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

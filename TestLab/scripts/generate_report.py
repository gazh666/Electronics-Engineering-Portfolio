"""生成综合工程测试报告（HTML）。

示例::

    conda run -n kaifa python -m scripts.generate_report --list
    conda run -n kaifa python -m scripts.generate_report --run-id <run_id>

只读取 SQLite 历史与对应运行目录，不重新执行测试。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import DATABASE_PATH, RESULTS_DIR  # noqa: E402
from reports.generator import (  # noqa: E402
    ReportError,
    generate_test_report,
)
from storage.sqlite_store import SQLiteStore  # noqa: E402


def _list_runs(db_path: Path, limit: int) -> int:
    if not db_path.is_file():
        print(f"数据库不存在: {db_path}")
        return 2
    store = SQLiteStore(db_path)
    runs = store.list_runs()[:limit]
    if not runs:
        print("数据库暂无运行记录。")
        return 0
    for run in runs:
        counts = store.get_run_summary(run["run_id"])
        print(
            f"{run['run_id']}  {run.get('suite_id') or '-':<18} "
            f"{run.get('status'):<10} PASS {counts['PASS']:>2} "
            f"FAIL {counts['FAIL']:>2} ERROR {counts['ERROR']:>2} "
            f"SKIP {counts['SKIP']:>2}  {run.get('started_at')}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 TestLab 综合工程测试报告")
    parser.add_argument("--run-id", help="要生成报告的运行编号")
    parser.add_argument("--list", action="store_true", help="列出最近运行记录")
    parser.add_argument("--limit", type=int, default=20, help="--list 显示条数")
    parser.add_argument("--db-path", default=str(DATABASE_PATH))
    parser.add_argument("--results-root", default=str(RESULTS_DIR))
    parser.add_argument(
        "--output-dir",
        default=None,
        help="报告输出目录（必须位于 results 内，默认 <results>/reports）",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db_path)
    if args.list or not args.run_id:
        if not args.run_id:
            print("未指定 --run-id，默认列出最近运行记录。")
        return _list_runs(db_path, args.limit)

    try:
        result = generate_test_report(
            args.run_id,
            db_path=db_path,
            results_root=Path(args.results_root),
            output_dir=args.output_dir,
        )
    except (ReportError, FileNotFoundError, ValueError) as exc:
        print(f"报告生成失败: {type(exc).__name__}: {exc}")
        return 2

    print("综合工程测试报告已生成：")
    print(f"  运行编号: {result['run_id']}")
    print(f"  文件: {result['path']}")
    print(f"  大小: {result['size_bytes']} 字节")
    print(f"  结论: {result['conclusion']}")
    print("  提示: 浏览器打开后可“打印 / 另存为 PDF”，报告不依赖网络资源。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

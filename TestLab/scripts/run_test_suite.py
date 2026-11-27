"""按测试方案批量执行用例（阶段七）。

示例::

    conda run -n kaifa python -m scripts.run_test_suite --list
    conda run -n kaifa python -m scripts.run_test_suite --suite SUITE-SMOKE
    conda run -n kaifa python -m scripts.run_test_suite --suite SUITE-REGRESSION

退出码：0 全部 PASS；1 存在 FAIL；2 存在 ERROR 或方案级错误；3 中断或无有效结果。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.case_loader import load_test_cases, load_test_suites  # noqa: E402
from engine.models import SuiteRunStatus  # noqa: E402
from engine.suite_runner import SuiteRunner, exit_code_for_results  # noqa: E402
from scripts.automation_context import (  # noqa: E402
    DEFAULT_CASES,
    DEFAULT_DB,
    DEFAULT_RESULTS,
    DEFAULT_SUITES,
    build_context,
)


def _list_suites(cases_path: Path, suites_path: Path) -> int:
    cases = load_test_cases(cases_path)
    suites = load_test_suites(suites_path, [case.case_id for case in cases])
    names = {case.case_id: case.name for case in cases}

    print(f"用例文件: {cases_path}（{len(cases)} 条）")
    print(f"方案文件: {suites_path}（{len(suites)} 个）\n")
    for suite in suites:
        print(f"{suite.suite_id}  {suite.name}")
        print(
            f"  用例数: {len(suite.case_ids)}  "
            f"stop_on_fail={suite.stop_on_fail}  stop_on_error={suite.stop_on_error}"
        )
        for case_id in suite.case_ids:
            print(f"    - {case_id} {names[case_id]}")
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="执行 TestLab 测试方案")
    parser.add_argument("--suite", help="测试方案编号，例如 SUITE-SMOKE")
    parser.add_argument("--list", action="store_true", help="列出方案与用例")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--suites", default=str(DEFAULT_SUITES))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--quiet", action="store_true", help="只输出最终汇总")
    args = parser.parse_args(argv)

    cases_path = Path(args.cases)
    suites_path = Path(args.suites)

    if args.list:
        return _list_suites(cases_path, suites_path)
    if not args.suite:
        parser.error("缺少 --suite（或使用 --list 查看可用方案）")

    cases = load_test_cases(cases_path)
    suites = load_test_suites(suites_path, [case.case_id for case in cases])
    suite = next((item for item in suites if item.suite_id == args.suite), None)
    if suite is None:
        available = ", ".join(item.suite_id for item in suites)
        print(f"错误: 找不到方案 {args.suite}，可用: {available}", file=sys.stderr)
        return 3

    def progress(current: int, total: int, result) -> None:
        if args.quiet:
            return
        print(
            f"[{current}/{total}] {result.status.value:5s} "
            f"{result.case_id} {result.case_name} ({result.duration_ms:.1f} ms)",
            flush=True,
        )

    with build_context(args.results, args.db, args.cases) as context:
        runner = SuiteRunner(context.runner, context.result_store, context.sqlite_store)
        run = runner.run_suite(suite, cases, progress_callback=progress)

    summary = run.summary
    print()
    print(f"方案: {run.suite_id} {run.suite_name}")
    print(f"运行编号: {run.run_id}")
    print(f"运行状态: {run.status.value}")
    print(
        f"用例统计: 总数={summary['total_cases']} 执行={summary['executed_cases']} "
        f"PASS={summary['pass_count']} FAIL={summary['fail_count']} "
        f"ERROR={summary['error_count']} SKIP={summary['skip_count']}"
    )
    for key in ("pass_rate", "completion_rate", "planned_pass_rate"):
        value = summary[key]
        print(f"{key}: {'N/A' if value is None else f'{value:.2f}%'}")
    print(f"总耗时: {summary['total_duration_ms']:.1f} ms")
    if run.stop_reason:
        print(f"停止原因: {run.stop_reason}")
    if run.suite_error:
        print(f"方案级错误: {run.suite_error}")
    print(f"结果目录: {Path(args.results) / ('run_' + run.run_id)}")

    if run.status is SuiteRunStatus.ABORTED:
        return 3
    if run.status is SuiteRunStatus.ERROR and not run.suite_error:
        # 清理失败或存储失败导致的 ERROR，优先按环境错误处理
        return 2
    return exit_code_for_results(run.results)


if __name__ == "__main__":
    raise SystemExit(main())

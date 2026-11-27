"""执行单个测试用例（阶段七）。

示例::

    conda run -n kaifa python -m scripts.run_single_test --case TC001
    conda run -n kaifa python -m scripts.run_single_test --case TC007 --json

退出码：0 PASS；1 FAIL；2 ERROR；3 SKIP 或未找到可执行结果。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.case_loader import load_test_cases  # noqa: E402
from engine.models import TestSuite  # noqa: E402
from engine.suite_runner import SuiteRunner, exit_code_for_results  # noqa: E402
from scripts.automation_context import (  # noqa: E402
    DEFAULT_CASES,
    DEFAULT_DB,
    DEFAULT_RESULTS,
    build_context,
)


def _print_result(result) -> None:
    print(f"用例: {result.case_id} {result.case_name}")
    print(f"执行编号: {result.run_id}")
    print(f"状态: {result.status.value}  耗时: {result.duration_ms:.1f} ms")
    print(
        f"预期状态: {result.expected_state} / 实际状态: "
        f"{result.actual_state or 'N/A'}"
    )

    raw = result.raw_data or {}
    metrics = result.metrics or {}
    if raw:
        print(
            f"Vin={raw.get('vin'):.4f} V, Vout={raw.get('vout'):.4f} V, "
            f"Iout={raw.get('iout'):.4f} A"
        )
        efficiency = metrics.get("efficiency_percent")
        efficiency_text = "N/A" if efficiency is None else f"{efficiency:.2f} %"
        print(
            f"Pin={raw.get('pin'):.4f} W, Pout={raw.get('pout'):.4f} W, "
            f"效率={efficiency_text}"
        )

    for check in result.checks:
        print(
            f"  - [{check.status.value}] {check.name}: 实际 {check.actual} "
            f"期望 {check.expected} | {check.message}"
        )

    if result.error_message:
        print(f"说明: {result.error_message}")
    if result.quality_issues:
        print(f"数据质量问题: {len(result.quality_issues)} 项")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="执行单个 TestLab 测试用例")
    parser.add_argument("--case", required=True, help="用例编号，例如 TC001")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = parser.parse_args(argv)

    cases = load_test_cases(args.cases)
    matched = next((case for case in cases if case.case_id == args.case), None)
    if matched is None:
        available = ", ".join(case.case_id for case in cases)
        print(f"错误: 找不到用例 {args.case}，可用: {available}", file=sys.stderr)
        return 3

    suite = TestSuite(
        suite_id="SINGLE",
        name="单用例执行",
        case_ids=(matched.case_id,),
        stop_on_fail=False,
        stop_on_error=False,
    )

    with build_context(args.results, args.db, args.cases) as context:
        runner = SuiteRunner(context.runner, context.result_store, context.sqlite_store)
        run = runner.run_suite(suite, cases)

    if args.json:
        print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
    else:
        for result in run.results:
            _print_result(result)
        summary = run.summary
        print(
            f"\n汇总: PASS={summary['pass_count']} FAIL={summary['fail_count']} "
            f"ERROR={summary['error_count']} SKIP={summary['skip_count']}"
        )
        print(f"结果目录: {Path(args.results) / ('run_' + run.run_id)}")

    return exit_code_for_results(run.results)


if __name__ == "__main__":
    raise SystemExit(main())

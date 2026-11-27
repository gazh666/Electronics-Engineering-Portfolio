"""故障注入命令行演示（阶段八，仅模拟环境）。

示例::

    conda run -n kaifa python -m scripts.fault_injection_demo --list
    conda run -n kaifa python -m scripts.fault_injection_demo --scenario F001
    conda run -n kaifa python -m scripts.fault_injection_demo --scenario F002
    conda run -n kaifa python -m scripts.fault_injection_demo --scenario F005

退出码：0 可靠性实验通过；1 实验不符合预期；2 运行/环境错误；3 参数错误。

注意：预期 ERROR 的实验实际得到正确 ERROR 时，实验本身可以成功退出，
但业务测试结果仍保持 ERROR，不会被改写为 PASS。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.performance_analyzer import PerformanceAnalyzer  # noqa: E402
from bench.virtual_test_bench import VirtualTestBench  # noqa: E402
from engine.case_loader import load_test_cases  # noqa: E402
from core.paths import RESULTS_DIR  # noqa: E402
from engine.models import TestSuite  # noqa: E402
from engine.suite_runner import SuiteRunner  # noqa: E402
from engine.test_runner import TestRunner  # noqa: E402
from instruments.manager import InstrumentManager  # noqa: E402
from models.virtual_dut import VirtualDUT  # noqa: E402
from reliability.fault_logger import FaultLogger, sanitize_event_value  # noqa: E402
from reliability.fault_models import (  # noqa: E402
    FaultScenarioLibrary,
    load_fault_scenarios,
)
from reliability.reliability_analyzer import (  # noqa: E402
    evaluate_suite_experiment,
    load_experiments,
    validate_experiment_coverage,
)
from reliability.retry_policy import RetryPolicy  # noqa: E402

INSTRUMENT_CONFIG = PROJECT_ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = PROJECT_ROOT / "configs" / "dut_config.yaml"
LIMITS_CONFIG = PROJECT_ROOT / "configs" / "performance_limits.yaml"
SCENARIO_CONFIG = PROJECT_ROOT / "configs" / "fault_scenarios.yaml"
RETRY_CONFIG = PROJECT_ROOT / "configs" / "retry_policy.yaml"
EXPERIMENT_CONFIG = PROJECT_ROOT / "configs" / "reliability_experiments.yaml"
CASE_CONFIG = PROJECT_ROOT / "configs" / "reliability_cases.yaml"
RESULT_ROOT = RESULTS_DIR / "fault_injection"

CASE_ID = "RC-RELIABILITY"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _list(library: FaultScenarioLibrary, experiments) -> None:
    print(f"故障场景文件: {SCENARIO_CONFIG}（{len(library.scenarios)} 个）")
    print(f"实验预期文件: {EXPERIMENT_CONFIG}（{len(experiments)} 个）\n")
    for scenario in library.scenarios:
        expectation = experiments.get(scenario.scenario_id)
        expected = expectation.expected_status if expectation else "缺少预期"
        print(
            f"{scenario.scenario_id}  {scenario.name}\n"
            f"  类型: {scenario.fault_type.value}  "
            f"位置: {scenario.target.value}:{scenario.operation}  "
            f"设备: {scenario.device or '-'}\n"
            f"  trigger_at={scenario.trigger_at}  occurrences={scenario.occurrences}  "
            f"offset={scenario.offset:g}  预期业务结果: {expected}"
        )
    print("\nNONE  正常无故障（基线对照）")


def _summarize_data(payload: dict | None) -> str:
    if not payload:
        return "（无）"
    keys = ("vin", "iin", "vout", "iout", "pin", "pout", "efficiency", "state", "source")
    subset = {key: payload.get(key) for key in keys}
    return json.dumps(
        sanitize_event_value(subset), ensure_ascii=False, allow_nan=False
    )


def _run(
    scenario_id: str,
    library: FaultScenarioLibrary,
    experiments,
    cases,
) -> tuple[int, dict]:
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    )
    run_dir = RESULT_ROOT / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    log_path = run_dir / "fault_events.jsonl"
    logger = FaultLogger(log_path)

    scenario = None if scenario_id == "NONE" else library.get(scenario_id)
    policy = RetryPolicy.from_yaml(RETRY_CONFIG)
    manager = InstrumentManager(INSTRUMENT_CONFIG)
    final_close_error: str | None = None
    results = []

    try:
        manager.open()
        bench = VirtualTestBench(manager, VirtualDUT.from_yaml(DUT_CONFIG))
        analyzer = PerformanceAnalyzer(LIMITS_CONFIG)
        runner = TestRunner(manager, bench, analyzer)
        scenarios = [] if scenario is None else [scenario]
        # F009 需要两个用例才能观察“清理失败后强制停止并记录 SKIP”
        case_ids = ("RC-RELIABILITY", "RC-RELIABILITY-B") if scenario_id == "F009" else (CASE_ID,)
        suite = TestSuite(
            suite_id=f"FAULT-{scenario_id}",
            name=f"故障注入演示 {scenario_id}",
            case_ids=case_ids,
            stop_on_fail=False,
            stop_on_error=False,
        )
        suite_runner = SuiteRunner(runner)
        run_result = suite_runner.run_suite(
            suite,
            [cases[case_id] for case_id in case_ids],
            run_id=run_id,
            fault_scenarios=scenarios,
            retry_policy=policy,
            fault_logger=logger,
        )
        results = list(run_result.results)
    finally:
        try:
            manager.close()
        except Exception as exc:  # 断开场景下会话已失效，关闭会失败
            final_close_error = f"{type(exc).__name__}: {exc}"
        logger.close()

    expectation = experiments[scenario_id]
    stopped_early = len(results) > 1 and all(
        item.status.value == "SKIP" for item in results[1:]
    )
    passed, reasons, actual = evaluate_suite_experiment(
        results,
        expectation,
        stopped_early=stopped_early if expectation.expect_forced_stop else None,
    )
    result = results[0]
    injection_events = [
        event
        for event in result.fault_events
        if event.get("event_type") == "FAULT_INJECTED"
    ]
    injected_types = sorted({str(event.get("fault_type")) for event in injection_events})

    print(f"故障场景: {scenario_id}" + (f"  {scenario.name}" if scenario else "  正常无故障"))
    if scenario is not None:
        print(
            f"注入位置: {scenario.target.value}:{scenario.operation}  "
            f"设备: {scenario.device or '-'}"
        )
        print(
            f"计划触发: trigger_at={scenario.trigger_at}, "
            f"occurrences={scenario.occurrences}；"
            f"实际触发: {len(injection_events)} 次（{', '.join(injected_types) or '-'}）"
        )
    else:
        print("注入位置: 未启用（默认关闭）")
    print(f"测试用例: {result.case_id} {result.case_name}")
    print(f"原始模型数据: {_summarize_data(result.original_model_data)}")
    print(f"注入后数据视图: {_summarize_data(result.observed_data or result.raw_data)}")
    print(
        f"重试次数: {result.retry_count}  恢复: {result.recovered}  "
        f"重试耗尽: {result.retry_exhausted}"
    )
    print(f"实际业务测试状态: {result.status.value}")
    if result.error_message:
        print(f"业务错误信息: {result.error_message}")
    print(
        f"可靠性实验预期: 状态={expectation.expected_status} "
        f"重试={expectation.expected_retry_count} "
        f"恢复={expectation.expected_recovered} "
        f"耗尽={expectation.expected_retry_exhausted} "
        f"清理={expectation.expected_cleanup_status}"
    )
    print(f"可靠性实验判定: {'PASS' if passed else 'FAIL'}")
    for reason in reasons:
        print(f"  - 不符合: {reason}")
    print(f"清理状态: {result.cleanup_status}")
    if result.cleanup_errors:
        for error in result.cleanup_errors:
            print(f"  - 清理错误: {error}")
    if len(results) > 1:
        print(
            f"后续任务: {len(results) - 1} 个，其中 "
            f"{sum(1 for item in results[1:] if item.status.value == 'SKIP')} 个已记录 SKIP"
        )
    if final_close_error:
        print(f"最终资源释放: 部分失败（保留记录，不视为已确认关闭）: {final_close_error}")
    print(f"事件日志: {log_path}")

    with (run_dir / "execution.log").open("a", encoding="utf-8") as file:
        file.write(f"{_now()} scenario={scenario_id} run_id={run_id}\n")
        file.write(f"{_now()} actual={json.dumps(actual, ensure_ascii=False)}\n")
        file.write(f"{_now()} experiment_passed={passed} reasons={reasons}\n")
        file.write(f"{_now()} final_close_error={final_close_error}\n")

    return (0 if passed else 1), {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "result": result,
        "actual": actual,
        "passed": passed,
        "reasons": reasons,
        "final_close_error": final_close_error,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TestLab 故障注入演示")
    parser.add_argument("--list", action="store_true", help="列出故障场景")
    parser.add_argument(
        "--scenario",
        help="故障场景编号（F001-F009，或 NONE 表示正常基线）",
    )
    args = parser.parse_args(argv)

    try:
        library = load_fault_scenarios(SCENARIO_CONFIG)
        experiments = load_experiments(EXPERIMENT_CONFIG)
        validate_experiment_coverage(["NONE", *library.ids()], experiments)
        cases = {case.case_id: case for case in load_test_cases(CASE_CONFIG)}
    except Exception as exc:
        print(f"配置错误: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.list:
        _list(library, experiments)
        return 0

    if not args.scenario:
        parser.error("缺少 --scenario（或使用 --list 查看可用场景）")
    scenario_id = args.scenario.strip().upper()
    if scenario_id not in experiments:
        available = ", ".join(experiments)
        print(f"错误: 未知场景 {scenario_id}，可用: {available}", file=sys.stderr)
        return 3
    case = cases.get(CASE_ID)
    if case is None:
        print(f"错误: 可靠性用例文件缺少 {CASE_ID}", file=sys.stderr)
        return 2

    try:
        code, _ = _run(scenario_id, library, experiments, cases)
    except Exception as exc:
        print(f"运行失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())

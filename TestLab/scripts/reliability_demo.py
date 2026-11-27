"""可靠性综合实验演示（阶段八，仅模拟环境）。

生成目录::

    results/reliability/run_<run_id>/
        scenario_results.csv
        fault_events.jsonl
        retry_statistics.json
        reliability_summary.json
        reliability_report.html
        execution.log
        charts/fault_types.svg
        charts/retries_by_scenario.svg
        charts/recovery_outcome.svg
        charts/experiment_outcome.svg
        charts/duration_by_scenario.svg

每个场景使用独立的 InstrumentManager 会话、VirtualDUT、注入器与重试
执行器；失败场景会真实产生异常，不会伪造 PASS。

退出码：0 全部实验通过；1 存在不符合预期的实验；2 运行/环境错误。
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.performance_analyzer import PerformanceAnalyzer  # noqa: E402
from bench.virtual_test_bench import VirtualTestBench  # noqa: E402
from core.paths import RESULTS_DIR  # noqa: E402
from engine.case_loader import load_test_cases  # noqa: E402
from engine.models import SuiteRunStatus, TestSuite  # noqa: E402
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
    ReliabilityAnalyzer,
    evaluate_suite_experiment,
    load_experiments,
    validate_experiment_coverage,
)
from reliability.retry_policy import RetryPolicy  # noqa: E402
from storage.sqlite_store import DEFAULT_DB_PATH, SQLiteStore  # noqa: E402

INSTRUMENT_CONFIG = PROJECT_ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = PROJECT_ROOT / "configs" / "dut_config.yaml"
LIMITS_CONFIG = PROJECT_ROOT / "configs" / "performance_limits.yaml"
SCENARIO_CONFIG = PROJECT_ROOT / "configs" / "fault_scenarios.yaml"
RETRY_CONFIG = PROJECT_ROOT / "configs" / "retry_policy.yaml"
EXPERIMENT_CONFIG = PROJECT_ROOT / "configs" / "reliability_experiments.yaml"
CASE_CONFIG = PROJECT_ROOT / "configs" / "reliability_cases.yaml"
RESULT_ROOT = RESULTS_DIR / "reliability"

CASE_A = "RC-RELIABILITY"
CASE_B = "RC-RELIABILITY-B"

SCENARIO_ORDER = (
    "NONE",
    "F001",
    "F002",
    "F003",
    "F004",
    "F005",
    "F006",
    "F007",
    "F008",
    "F009",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _append_log(path: Path, message: str) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(f"{_now()} {message}\n")


def _bar_chart(
    title: str,
    labels: Sequence[str],
    values: Sequence[float],
    path: Path,
    *,
    color: str = "#2563eb",
    unit: str = "",
) -> None:
    """生成纯 SVG 柱状图（不依赖第三方绘图库）。"""
    width, height = 760, 420
    left, right, top, bottom = 70, 30, 60, 110
    plot_width = width - left - right
    plot_height = height - top - bottom
    maximum = max([float(value) for value in values] or [0.0])
    axis_max = maximum if maximum > 0 else 1.0
    count = max(len(labels), 1)
    slot = plot_width / count
    bar_width = slot * 0.58

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{html.escape(title)}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2:.1f}" y="34" text-anchor="middle" '
        f'font-family="Segoe UI, Arial, sans-serif" font-size="18" '
        f'font-weight="600" fill="#0f172a">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top + plot_height}" '
        f'x2="{left + plot_width}" y2="{top + plot_height}" stroke="#94a3b8"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" '
        f'y2="{top + plot_height}" stroke="#94a3b8"/>',
        f'<text x="{left - 10}" y="{top + 4}" text-anchor="end" '
        f'font-family="Segoe UI, Arial, sans-serif" font-size="11" '
        f'fill="#475569">{axis_max:g}{html.escape(unit)}</text>',
        f'<text x="{left - 10}" y="{top + plot_height + 4}" text-anchor="end" '
        f'font-family="Segoe UI, Arial, sans-serif" font-size="11" fill="#475569">0</text>',
        f'<line x1="{left}" y1="{top}" x2="{left + plot_width}" y2="{top}" '
        f'stroke="#e2e8f0" stroke-dasharray="4 4"/>',
    ]

    for index, (label, value) in enumerate(zip(labels, values)):
        value = float(value)
        bar_height = plot_height * (value / axis_max) if axis_max else 0.0
        x = left + slot * index + (slot - bar_width) / 2
        y = top + plot_height - bar_height
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
            f'height="{max(bar_height, 0.0):.1f}" rx="3" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{y - 6:.1f}" '
            f'text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
            f'font-size="12" fill="#0f172a">{value:g}{html.escape(unit)}</text>'
        )
        short = label if len(label) <= 12 else label[:11] + "…"
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" '
            f'y="{top + plot_height + 24}" text-anchor="middle" '
            f'font-family="Segoe UI, Arial, sans-serif" font-size="11" '
            f'fill="#334155" transform="rotate(-25 '
            f'{x + bar_width / 2:.1f} {top + plot_height + 24})">'
            f"{html.escape(short)}</text>"
        )

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_charts(
    charts_dir: Path,
    scenario_rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Path]:
    charts: dict[str, Path] = {}
    charts["fault_types"] = charts_dir / "fault_types.svg"
    type_counts = summary.get("injected_fault_type_counts") or {}
    _bar_chart(
        "注入故障类型分布（次数）",
        list(type_counts) or ["无"],
        list(type_counts.values()) or [0],
        charts["fault_types"],
        color="#2563eb",
    )

    charts["retries"] = charts_dir / "retries_by_scenario.svg"
    _bar_chart(
        "各场景重试次数",
        [row["scenario_id"] for row in scenario_rows],
        [row["actual_retry_count"] for row in scenario_rows],
        charts["retries"],
        color="#7c3aed",
    )

    charts["recovery"] = charts_dir / "recovery_outcome.svg"
    _bar_chart(
        "重试恢复结果（按操作去重）",
        ["恢复成功", "重试耗尽"],
        [
            summary.get("recovered_operations", 0),
            summary.get("retry_exhausted_count", 0),
        ],
        charts["recovery"],
        color="#059669",
    )

    charts["experiment"] = charts_dir / "experiment_outcome.svg"
    _bar_chart(
        "可靠性实验判定",
        ["通过", "失败"],
        [
            summary.get("experiment_pass_count", 0),
            summary.get("experiment_fail_count", 0),
        ],
        charts["experiment"],
        color="#ea580c",
    )

    charts["duration"] = charts_dir / "duration_by_scenario.svg"
    _bar_chart(
        "各场景执行耗时（毫秒）",
        [row["scenario_id"] for row in scenario_rows],
        [round(row["duration_ms"], 3) for row in scenario_rows],
        charts["duration"],
        color="#0f766e",
        unit=" ms",
    )
    return charts


def _format_data(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "（无）"
    keys = ("vin", "iin", "vout", "iout", "pin", "pout", "efficiency", "state", "source")
    subset = {key: payload.get(key) for key in keys}
    return json.dumps(sanitize_event_value(subset), ensure_ascii=False, allow_nan=False)


def _run_scenario(
    scenario_id: str,
    library: FaultScenarioLibrary,
    experiments,
    cases,
    policy: RetryPolicy,
    logger: FaultLogger,
    sqlite: SQLiteStore,
    demo_run_id: str,
    execution_log: Path,
) -> dict[str, Any]:
    expectation = experiments[scenario_id]
    scenario = None if scenario_id == "NONE" else library.get(scenario_id)
    scenarios: list[Any] = [] if scenario is None else [scenario]
    run_id = f"{demo_run_id}-{scenario_id}"

    manager = InstrumentManager(INSTRUMENT_CONFIG)
    final_close_error: str | None = None
    results: list[Any] = []

    _append_log(
        execution_log,
        f"START scenario={scenario_id} run_id={run_id} "
        f"expected_status={expectation.expected_status}",
    )
    try:
        manager.open()
        bench = VirtualTestBench(manager, VirtualDUT.from_yaml(DUT_CONFIG))
        analyzer = PerformanceAnalyzer(LIMITS_CONFIG)
        runner = TestRunner(manager, bench, analyzer)

        if scenario_id == "F009":
            # 两个用例：第一个清理失败后必须强制跳过第二个
            suite = TestSuite(
                suite_id="REL-F009",
                name="F009 清理失败强制停止验证",
                case_ids=(CASE_A, CASE_B),
                stop_on_fail=False,
                stop_on_error=False,
            )
            suite_runner = SuiteRunner(runner)
            run_result = suite_runner.run_suite(
                suite,
                [cases[CASE_A], cases[CASE_B]],
                run_id=run_id,
                fault_scenarios=scenarios,
                retry_policy=policy,
                fault_logger=logger,
            )
            results = list(run_result.results)
        else:
            runner.configure_reliability(
                scenarios, retry_policy=policy, fault_logger=logger
            )
            results = [runner.run_case(cases[CASE_A], run_id, 0)]
    except Exception as exc:
        _append_log(
            execution_log,
            f"ERROR scenario={scenario_id} {type(exc).__name__}: {exc}",
        )
        raise
    finally:
        try:
            manager.close()
        except Exception as exc:
            final_close_error = f"{type(exc).__name__}: {exc}"
            _append_log(
                execution_log,
                f"FINAL_CLOSE_NOT_VERIFIED scenario={scenario_id} {final_close_error}",
            )

    stopped_early = len(results) > 1 and all(
        result.status.value == "SKIP" for result in results[1:]
    )
    passed, reasons, actual = evaluate_suite_experiment(
        results,
        expectation,
        stopped_early=stopped_early if expectation.expect_forced_stop else None,
    )
    primary = results[0]
    events = [event for event in logger.events if event.get("run_id") == run_id]
    injection_count = sum(
        1 for event in events if event.get("event_type") == "FAULT_INJECTED"
    )
    retry_events = sum(
        1 for event in events if event.get("event_type") == "RETRY_SCHEDULED"
    )
    scenario_row = {
        "scenario_id": scenario_id,
        "name": expectation.name,
        "case_id": primary.case_id,
        "expected_status": expectation.expected_status,
        "actual_status": primary.status.value,
        "experiment_passed": passed,
        "expected_retry_count": expectation.expected_retry_count,
        "actual_retry_count": primary.retry_count,
        "recovered": primary.recovered,
        "retry_exhausted": primary.retry_exhausted,
        "fault_injection_count": injection_count,
        "retry_event_count": retry_events,
        "expected_cleanup_status": expectation.expected_cleanup_status,
        "actual_cleanup_status": primary.cleanup_status,
        "stopped_early": stopped_early,
        "skipped_cases": sum(1 for result in results if result.status.value == "SKIP"),
        "duration_ms": sum(result.duration_ms for result in results),
        "final_resource_close": (
            "OK" if final_close_error is None else "ERROR_NOT_VERIFIED"
        ),
        "final_close_error": final_close_error or "",
        "reasons": "; ".join(reasons),
        "error_message": primary.error_message or "",
        "original_vout": (primary.original_model_data or {}).get("vout"),
        "observed_vout": (primary.raw_data or {}).get("vout"),
        "observed_iout": (primary.raw_data or {}).get("iout"),
    }

    summary = {
        "scenario_id": scenario_id,
        "status": primary.status.value,
        "expected_status": expectation.expected_status,
        "experiment_passed": passed,
        "reasons": reasons,
        "actual": actual,
        "final_close_error": final_close_error,
    }
    sqlite.start_run(
        run_id,
        suite_id=f"REL-{scenario_id}",
        suite_name=expectation.name,
        planned_count=len(results),
        started_at=primary.started_at,
    )
    for result in results:
        sqlite.save_result(result)
    sqlite.save_fault_events(events)
    sqlite.finish_run(
        run_id,
        SuiteRunStatus.COMPLETED.value if passed else SuiteRunStatus.ERROR.value,
        summary,
    )

    _append_log(
        execution_log,
        f"END scenario={scenario_id} status={primary.status.value} "
        f"experiment={'PASS' if passed else 'FAIL'} "
        f"reasons={reasons}",
    )
    print(
        f"{scenario_id:<5} 业务={primary.status.value:<5} "
        f"重试={primary.retry_count} 恢复={primary.recovered} "
        f"清理={primary.cleanup_status:<13} "
        f"实验={'PASS' if passed else 'FAIL'}"
    )
    for reason in reasons:
        print(f"      - {reason}")

    scenario_row["events"] = events
    scenario_row["results"] = results
    return scenario_row


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields = [
        "scenario_id",
        "name",
        "case_id",
        "expected_status",
        "actual_status",
        "experiment_passed",
        "expected_retry_count",
        "actual_retry_count",
        "recovered",
        "retry_exhausted",
        "fault_injection_count",
        "retry_event_count",
        "expected_cleanup_status",
        "actual_cleanup_status",
        "stopped_early",
        "skipped_cases",
        "duration_ms",
        "final_resource_close",
        "final_close_error",
        "reasons",
        "error_message",
        "original_vout",
        "observed_vout",
        "observed_iout",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def _html_report(
    run_id: str,
    rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    retry_stats: dict[str, Any],
    reconciliation: dict[str, Any],
    charts: dict[str, Path],
    report_path: Path,
) -> None:
    def e(value: Any) -> str:
        return html.escape(str(value))

    scenario_table_rows = "\n".join(
        "<tr>"
        f"<td>{e(row['scenario_id'])}</td>"
        f"<td>{e(row['name'])}</td>"
        f"<td>{e(row['expected_status'])}</td>"
        f"<td class=\"{'ok' if row['experiment_passed'] else 'bad'}\">"
        f"{e(row['actual_status'])}</td>"
        f"<td>{e(row['actual_retry_count'])}</td>"
        f"<td>{e(row['recovered'])}</td>"
        f"<td>{e(row['fault_injection_count'])}</td>"
        f"<td>{e(row['actual_cleanup_status'])}</td>"
        f"<td class=\"{'ok' if row['experiment_passed'] else 'bad'}\">"
        f"{'PASS' if row['experiment_passed'] else 'FAIL'}</td>"
        f"<td>{e(row['reasons'] or '-')}</td>"
        "</tr>"
        for row in rows
    )

    type_rows = "\n".join(
        f"<tr><td>{e(key)}</td><td>{e(value)}</td></tr>"
        for key, value in (summary.get("injected_fault_type_counts") or {}).items()
    ) or "<tr><td colspan=\"2\">无注入</td></tr>"

    coverage_rows = "\n".join(
        f"<tr><td>{e(item['fault_type'])}</td>"
        f"<td>{e(item['triggered'])}</td>"
        f"<td>{'是' if item['covered'] else '否'}</td></tr>"
        for item in summary.get("fault_detection_coverage") or []
    ) or "<tr><td colspan=\"3\">未提供预期类型</td></tr>"

    chart_html = "\n".join(
        f'<figure><img src="charts/{e(path.name)}" alt="{e(path.stem)}"/>'
        f"<figcaption>{e(path.stem)}</figcaption></figure>"
        for path in charts.values()
    )

    recovery_rate = summary.get("recovery_rate")
    report = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>TestLab 可靠性实验报告 {e(run_id)}</title>
<style>
:root {{ color-scheme: light; }}
body {{ margin:0; font-family:"Segoe UI","Microsoft YaHei",Arial,sans-serif;
       background:#f8fafc; color:#0f172a; }}
header {{ background:#0f172a; color:#f8fafc; padding:28px 40px; }}
header h1 {{ margin:0 0 6px; font-size:24px; }}
header p {{ margin:0; color:#cbd5e1; font-size:13px; }}
main {{ max-width:1180px; margin:0 auto; padding:28px 24px 60px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
         gap:14px; margin-bottom:24px; }}
.card {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px;
        padding:16px 18px; }}
.card span {{ display:block; color:#64748b; font-size:12px; margin-bottom:6px; }}
.card strong {{ font-size:24px; }}
section {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px;
          padding:20px 22px; margin-bottom:22px; }}
h2 {{ font-size:17px; margin:0 0 14px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #e2e8f0;
        vertical-align:top; }}
th {{ background:#f1f5f9; color:#334155; font-weight:600; }}
.ok {{ color:#047857; font-weight:600; }}
.bad {{ color:#b91c1c; font-weight:600; }}
.charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr));
          gap:16px; }}
figure {{ margin:0; border:1px solid #e2e8f0; border-radius:10px; padding:10px;
         background:#fff; }}
figure img {{ width:100%; height:auto; display:block; }}
figcaption {{ font-size:12px; color:#64748b; text-align:center; padding-top:6px; }}
.note {{ color:#475569; font-size:13px; line-height:1.7; }}
code {{ background:#f1f5f9; padding:1px 5px; border-radius:4px; }}
</style>
</head>
<body>
<header>
  <h1>TestLab 可靠性实验报告</h1>
  <p>运行编号 {e(run_id)} · 数据模式 {e(summary.get('data_mode'))} · 生成时间 {e(_now())}</p>
</header>
<main>
<div class="cards">
  <div class="card"><span>实验场景</span><strong>{e(summary.get('scenario_count'))}</strong></div>
  <div class="card"><span>故障注入次数</span><strong>{e(summary.get('total_fault_injections'))}</strong></div>
  <div class="card"><span>重试次数</span><strong>{e(summary.get('retry_count'))}</strong></div>
  <div class="card"><span>恢复率</span><strong>{e('-' if recovery_rate is None else f'{recovery_rate:.1f}%')}</strong></div>
  <div class="card"><span>清理未确认</span><strong>{e(summary.get('cleanup_failure_count'))}</strong></div>
  <div class="card"><span>实验通过 / 失败</span><strong>{e(summary.get('experiment_pass_count'))} / {e(summary.get('experiment_fail_count'))}</strong></div>
</div>

<section>
<h2>场景结果与实验判定</h2>
<table>
<thead><tr><th>场景</th><th>名称</th><th>预期</th><th>业务状态</th><th>重试</th>
<th>恢复</th><th>注入</th><th>清理</th><th>实验</th><th>差异原因</th></tr></thead>
<tbody>{scenario_table_rows}</tbody>
</table>
</section>

<section>
<h2>统计图表</h2>
<div class="charts">{chart_html}</div>
</section>

<section>
<h2>故障类型与覆盖</h2>
<table><thead><tr><th>故障类型</th><th>注入次数</th></tr></thead>
<tbody>{type_rows}</tbody></table>
<p class="note">预期故障类型覆盖：</p>
<table><thead><tr><th>类型</th><th>实际触发</th><th>已覆盖</th></tr></thead>
<tbody>{coverage_rows}</tbody></table>
</section>

<section>
<h2>重试统计</h2>
<table>
<tr><th>可重试操作数</th><td>{e(summary.get('retry_eligible_operations'))}</td></tr>
<tr><th>恢复操作数</th><td>{e(summary.get('recovered_operations'))}</td></tr>
<tr><th>重试耗尽操作数</th><td>{e(summary.get('retry_exhausted_count'))}</td></tr>
<tr><th>安全重试总次数</th><td>{e(summary.get('retry_count'))}</td></tr>
<tr><th>重试额外等待</th><td>{e(summary.get('retry_overhead_ms'))} ms</td></tr>
<tr><th>强制停止次数</th><td>{e(summary.get('forced_stop_count'))}</td></tr>
</table>
</section>

<section>
<h2>存储一致性</h2>
<p class="note">JSONL 事件数 {e(reconciliation.get('jsonl_event_count'))}，
SQLite 事件数 {e(reconciliation.get('sqlite_event_count'))}，
一致性：<strong class="{'ok' if reconciliation.get('reconciled') else 'bad'}">
{e('通过' if reconciliation.get('reconciled') else '不一致')}</strong>。</p>
</section>

<section>
<h2>结论与限制</h2>
<p class="note">
业务测试状态与可靠性实验结论严格分离：预期为 ERROR 的持续超时、断开、
非法数据与清理失败实验，即使实验判定通过，业务结果仍保持 ERROR，
不会改写为 PASS。<br/>
本报告全部数据来自 PyVISA-sim 与 VirtualDUT 行为模型，属于受控模拟实验，
<strong>不能</strong>作为真实仪器 MTBF/MTTR、抖动容限或安全认证依据。<br/>
F003 断开后无法回读输出状态，F009 注入关闭失败，两者只能记录
<code>NOT_VERIFIED</code>，不能断言硬件已关闭。<br/>
重试仅覆盖白名单只读查询与可恢复超时；写入、断开、非法数据与清理失败
均不自动重试。
</p>
</section>
</main>
</body>
</html>
"""
    report_path.write_text(report, encoding="utf-8")


def _reconcile(
    logger: FaultLogger,
    sqlite: SQLiteStore,
    run_ids: Iterable[str],
) -> dict[str, Any]:
    run_id_set = list(run_ids)
    jsonl_events = [
        event for event in logger.events if event.get("run_id") in set(run_id_set)
    ]
    sqlite_counts = {
        run_id: sqlite.count_fault_events(run_id) for run_id in run_id_set
    }
    sqlite_total = sum(sqlite_counts.values())
    return {
        "jsonl_event_count": len(jsonl_events),
        "sqlite_event_count": sqlite_total,
        "sqlite_counts_by_run": sqlite_counts,
        "reconciled": len(jsonl_events) == sqlite_total,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TestLab 可靠性综合实验")
    parser.add_argument(
        "--scenario",
        action="append",
        help="只运行指定场景（可重复）；默认运行 NONE 与 F001-F009",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="SQLite 历史数据库路径（默认 results/testlab.db）",
    )
    args = parser.parse_args(argv)

    try:
        library = load_fault_scenarios(SCENARIO_CONFIG)
        experiments = load_experiments(EXPERIMENT_CONFIG)
        validate_experiment_coverage(["NONE", *library.ids()], experiments)
        cases = {case.case_id: case for case in load_test_cases(CASE_CONFIG)}
        policy = RetryPolicy.from_yaml(RETRY_CONFIG)
    except Exception as exc:
        print(f"配置错误: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    selected = list(SCENARIO_ORDER)
    if args.scenario:
        selected = [sid.strip().upper() for sid in args.scenario]
        unknown = [sid for sid in selected if sid not in experiments]
        if unknown:
            print(f"未知场景: {', '.join(unknown)}", file=sys.stderr)
            return 2

    demo_run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    )
    run_dir = RESULT_ROOT / f"run_{demo_run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    execution_log = run_dir / "execution.log"
    logger = FaultLogger(run_dir / "fault_events.jsonl")
    sqlite = SQLiteStore(args.db)

    print(f"可靠性实验运行: {demo_run_id}")
    print(f"SQLite: {sqlite.db_path}（已有历史保留）")
    print(f"输出目录: {run_dir}\n")

    scenario_rows: list[dict[str, Any]] = []
    harness_error: str | None = None
    try:
        for scenario_id in selected:
            row = _run_scenario(
                scenario_id,
                library,
                experiments,
                cases,
                policy,
                logger,
                sqlite,
                demo_run_id,
                execution_log,
            )
            scenario_rows.append(row)
    except Exception as exc:
        harness_error = f"{type(exc).__name__}: {exc}"
        _append_log(execution_log, f"HARNESS_ERROR {harness_error}")
        print(f"运行失败: {harness_error}", file=sys.stderr)
    finally:
        logger.close()

    if harness_error is not None:
        return 2

    analyzer_results = [
        {
            "scenario_id": row["scenario_id"],
            "case_id": row["case_id"],
            "status": row["actual_status"],
            "retry_count": row["actual_retry_count"],
            "recovered": row["recovered"],
            "retry_exhausted": row["retry_exhausted"],
            "cleanup_status": row["actual_cleanup_status"],
            "fault_injected": row["fault_injection_count"] > 0,
            "cleanup_failed": row["actual_cleanup_status"] == "NOT_VERIFIED",
            "duration_ms": row["duration_ms"],
            "forced_stop": row["stopped_early"],
            "experiment_passed": row["experiment_passed"],
        }
        for row in scenario_rows
    ]
    expected_types = [
        library.get(row["scenario_id"]).fault_type.value
        for row in scenario_rows
        if row["scenario_id"] != "NONE"
    ]
    summary = ReliabilityAnalyzer().summarize(
        logger.events,
        analyzer_results,
        expected_fault_types=sorted(set(expected_types)),
    )

    reconciliation = _reconcile(
        logger,
        sqlite,
        [f"{demo_run_id}-{row['scenario_id']}" for row in scenario_rows],
    )
    retry_stats = {
        "policy": {
            "enabled": policy.enabled,
            "max_attempts": policy.max_attempts,
            "initial_delay_seconds": policy.initial_delay,
            "backoff_multiplier": policy.multiplier,
            "max_delay_seconds": policy.max_delay,
            "retryable_categories": [item.value for item in policy.retryable_categories],
            "allowed_query_commands": list(policy.allowed_query_commands),
            "retry_writes": policy.retry_writes,
            "retry_invalid_data": policy.retry_invalid_data,
        },
        "per_scenario": {
            row["scenario_id"]: {
                "retry_count": row["actual_retry_count"],
                "recovered": row["recovered"],
                "retry_exhausted": row["retry_exhausted"],
            }
            for row in scenario_rows
        },
        "aggregate": {
            "retry_count": summary["retry_count"],
            "retry_eligible_operations": summary["retry_eligible_operations"],
            "recovered_operations": summary["recovered_operations"],
            "retry_exhausted_count": summary["retry_exhausted_count"],
            "recovery_rate": summary["recovery_rate"],
            "retry_overhead_ms": summary["retry_overhead_ms"],
        },
    }

    _write_csv(run_dir / "scenario_results.csv", scenario_rows)
    (run_dir / "retry_statistics.json").write_text(
        json.dumps(
            sanitize_event_value(retry_stats), ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    reliability_payload = {
        "run_id": demo_run_id,
        "generated_at": _now(),
        "data_mode": summary["data_mode"],
        "environment": "PyVISA-sim + VirtualDUT（仅模拟）",
        "selected_scenarios": selected,
        "scenario_results": [
            {key: value for key, value in row.items() if key not in ("events", "results")}
            for row in scenario_rows
        ],
        "summary": summary,
        "retry_statistics": retry_stats,
        "storage_reconciliation": reconciliation,
        "limitations": [
            "模拟环境实验，不代表真实设备 MTBF/MTTR 或安全认证。",
            "F003 断开与 F009 关闭失败只能记录 NOT_VERIFIED。",
            "业务 ERROR/FAIL 不会被改写为 PASS；实验判定独立计算。",
            "重试只覆盖白名单只读查询与可恢复超时。",
        ],
    }
    (run_dir / "reliability_summary.json").write_text(
        json.dumps(
            sanitize_event_value(reliability_payload), ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )

    charts = _write_charts(run_dir / "charts", scenario_rows, summary)
    _html_report(
        demo_run_id,
        scenario_rows,
        summary,
        retry_stats,
        reconciliation,
        charts,
        run_dir / "reliability_report.html",
    )

    passed_count = sum(1 for row in scenario_rows if row["experiment_passed"])
    failed_count = len(scenario_rows) - passed_count
    recovery_rate = summary["recovery_rate"]
    recovery_text = (
        "-" if recovery_rate is None else f"{recovery_rate:.1f}%"
    )
    print("\n汇总")
    print(f"  场景: {len(scenario_rows)}  实验通过: {passed_count}  失败: {failed_count}")
    print(f"  故障注入: {summary['total_fault_injections']} 次")
    print(
        f"  重试: {summary['retry_count']} 次  恢复率: {recovery_text}"
    )
    print(f"  清理未确认: {summary['cleanup_failure_count']}  强制停止: {summary['forced_stop_count']}")
    print(f"  存储一致性: {'PASS' if reconciliation['reconciled'] else 'FAIL'} "
          f"(JSONL={reconciliation['jsonl_event_count']}, SQLite={reconciliation['sqlite_event_count']})")
    print(f"  报告: {run_dir / 'reliability_report.html'}")
    _append_log(
        execution_log,
        f"SUMMARY passed={passed_count} failed={failed_count} "
        f"reconciled={reconciliation['reconciled']}",
    )
    return 0 if failed_count == 0 and reconciliation["reconciled"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

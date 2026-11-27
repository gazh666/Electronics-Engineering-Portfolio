"""TestLab 发布验收：用临时结果目录检查核心功能，不污染真实历史。

示例::

    conda run -n kaifa python -m scripts.verify_release

输出每个验收项目的真实结果；核心验收失败返回非零退出码。
Docker/Linux/CI 等无法在本机执行的项目标记 NOT_VERIFIED，不误报通过。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3  # noqa: E402

import yaml  # noqa: E402

from contextlib import closing  # noqa: E402

from core.paths import CONFIG_DIR  # noqa: E402
from engine.case_loader import load_test_cases, load_test_suites  # noqa: E402
from engine.models import SuiteRunStatus, TestSuite  # noqa: E402
from engine.suite_runner import SuiteRunner  # noqa: E402
from instruments.manager import InstrumentManager  # noqa: E402
from models.virtual_dut import VirtualDUT  # noqa: E402
from reports.generator import generate_test_report  # noqa: E402
from reliability.fault_models import load_fault_scenarios  # noqa: E402
from reliability.retry_policy import load_retry_policy  # noqa: E402
from scripts.automation_context import build_context  # noqa: E402

INSTRUMENTS = CONFIG_DIR / "instruments.yaml"
DUT_CONFIG = CONFIG_DIR / "dut_config.yaml"
LIMITS = CONFIG_DIR / "performance_limits.yaml"
CASES = CONFIG_DIR / "test_cases.yaml"
SUITES = CONFIG_DIR / "test_suites.yaml"
FAULTS = CONFIG_DIR / "fault_scenarios.yaml"
RETRY = CONFIG_DIR / "retry_policy.yaml"
RELIABILITY_CASES = CONFIG_DIR / "reliability_cases.yaml"
RELIABILITY_EXPERIMENTS = CONFIG_DIR / "reliability_experiments.yaml"

CONFIG_FILES = (
    INSTRUMENTS,
    DUT_CONFIG,
    LIMITS,
    CASES,
    SUITES,
    FAULTS,
    RETRY,
    RELIABILITY_CASES,
    RELIABILITY_EXPERIMENTS,
)

REQUIRED_TABLES = {"runs", "test_results", "check_results", "fault_events"}


def check_python() -> str:
    if sys.version_info < (3, 11):
        raise AssertionError(f"需要 Python >= 3.11，当前 {sys.version.split()[0]}")
    return sys.version.split()[0]


def check_imports() -> str:
    import importlib

    modules = [
        "core.paths",
        "instruments",
        "models.virtual_dut",
        "bench.virtual_test_bench",
        "analysis.metrics",
        "engine.test_runner",
        "engine.suite_runner",
        "storage.result_store",
        "storage.sqlite_store",
        "reliability.fault_models",
        "ui.service",
        "reports.generator",
    ]
    for name in modules:
        importlib.import_module(name)
    return f"{len(modules)} 个核心模块导入成功"


def check_configs() -> str:
    missing = [str(path) for path in CONFIG_FILES if not path.is_file()]
    if missing:
        raise AssertionError(f"配置文件缺失: {', '.join(missing)}")
    for path in CONFIG_FILES:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise AssertionError(f"配置不是映射: {path}")
    return f"{len(CONFIG_FILES)} 个 YAML 配置存在且可解析"


def check_instruments() -> str:
    with InstrumentManager(INSTRUMENTS) as manager:
        resources = manager.discover()
        for role in ("psu", "dmm", "load"):
            manager.resource_name(role)
    if len(resources) < 3:
        raise AssertionError(f"虚拟仪器资源不足: {resources}")
    return f"发现 {len(resources)} 个资源；psu/dmm/load 可解析"


def check_virtual_dut() -> str:
    dut = VirtualDUT.from_yaml(DUT_CONFIG)
    result = dut.calculate(12.0, 1.0)
    state = str(getattr(result.state, "value", result.state))
    if state != "NORMAL":
        raise AssertionError(f"12 V/1 A 计算状态异常: {state}")
    if result.vout is None or not (4.9 <= result.vout <= 5.1):
        raise AssertionError(f"输出电压异常: {result.vout}")
    return f"NORMAL, vout={result.vout:.4f} V, efficiency={result.efficiency:.4f}"


def check_automation_and_faults_and_report(tmp: Path) -> tuple[str, str]:
    """在临时目录执行冒烟方案、F001 故障注入并生成综合报告。"""
    cases = load_test_cases(CASES)
    suites = load_test_suites(SUITES, [case.case_id for case in cases])
    smoke = next((item for item in suites if item.suite_id == "SUITE-SMOKE"), None)
    if smoke is None:
        raise AssertionError("找不到 SUITE-SMOKE 方案")

    results_root = tmp / "results"
    database = tmp / "testlab.db"
    with build_context(results_root / "automation", database, CASES) as context:
        runner = SuiteRunner(
            context.runner, context.result_store, context.sqlite_store
        )
        run = runner.run_suite(smoke, cases)
        if run.status is not SuiteRunStatus.COMPLETED:
            raise AssertionError(f"SUITE-SMOKE 运行状态异常: {run.status}")
        if run.summary["error_count"] or not run.summary["pass_count"]:
            raise AssertionError(f"SUITE-SMOKE 结果异常: {run.summary}")

        library = load_fault_scenarios(FAULTS)
        policy = load_retry_policy(RETRY)
        rel_cases = {case.case_id: case for case in load_test_cases(RELIABILITY_CASES)}
        rel_suite = TestSuite(
            suite_id="VERIFY-F001",
            name="发布验收故障注入",
            case_ids=("RC-RELIABILITY",),
            stop_on_fail=False,
            stop_on_error=False,
        )
        rel_run = SuiteRunner(context.runner).run_suite(
            rel_suite,
            [rel_cases["RC-RELIABILITY"]],
            run_id="verify_f001",
            fault_scenarios=[library.get("F001")],
            retry_policy=policy,
        )
        first = rel_run.results[0]
        injected = [
            event
            for event in first.fault_events
            if event.get("event_type") == "FAULT_INJECTED"
        ]
        if not first.fault_injected or not injected:
            raise AssertionError("F001 未产生故障注入事件")

    report = generate_test_report(
        run.run_id, db_path=database, results_root=results_root
    )
    path = Path(report["path"])
    if not path.is_file() or path.stat().st_size == 0:
        raise AssertionError("综合报告未生成或为空")
    if run.run_id not in path.read_text(encoding="utf-8"):
        raise AssertionError("报告内容缺少运行编号")

    with closing(sqlite3.connect(database)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = REQUIRED_TABLES - tables
    if missing:
        raise AssertionError(f"数据库缺少表: {', '.join(sorted(missing))}")

    automation = (
        f"SUITE-SMOKE PASS={run.summary['pass_count']} "
        f"FAIL={run.summary['fail_count']} ERROR={run.summary['error_count']}"
    )
    fault = f"F001 注入事件 {len(injected)} 次，业务状态 {first.status.value}"
    return f"{automation}；{fault}；报告 {path.name}"


def check_version() -> str:
    version_file = PROJECT_ROOT / "VERSION"
    if not version_file.is_file():
        raise AssertionError("缺少 VERSION 文件")
    value = version_file.read_text(encoding="utf-8").strip()
    if not value:
        raise AssertionError("VERSION 为空")
    return value


def check_docker() -> str | None:
    """返回说明字符串；docker 不可用时由调用方标记 NOT_VERIFIED。"""
    executable = shutil.which("docker")
    if not executable:
        return None
    try:
        version = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if version.returncode != 0:
        return None
    return version.stdout.strip() or "docker 可用"


def main(argv: list[str] | None = None) -> int:
    del argv
    print("TestLab 发布验收（临时结果目录，不污染真实历史）")
    print("=" * 68)

    failures = 0

    def run_check(name: str, func: Callable[[], str]) -> None:
        nonlocal failures
        try:
            detail = func()
        except Exception as exc:  # 验收脚本必须报告而不是崩溃
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"[PASS] {name}: {detail}")

    run_check("Python 版本", check_python)
    run_check("核心依赖导入", check_imports)
    run_check("配置文件", check_configs)
    run_check("虚拟仪器资源发现", check_instruments)
    run_check("VirtualDUT 模型计算", check_virtual_dut)
    run_check("项目版本文件", check_version)

    with tempfile.TemporaryDirectory(prefix="testlab_verify_") as tmp_name:
        tmp = Path(tmp_name)

        def core_flow() -> str:
            return check_automation_and_faults_and_report(tmp)

        run_check("自动化执行 + 故障注入 + 数据库 + 综合报告", core_flow)

    docker = check_docker()
    if docker:
        print(f"[NOT_VERIFIED] Docker 镜像构建/运行：docker 命令可用（{docker}），"
              "本脚本不执行 build/up，需人工验证。")
    else:
        print("[NOT_VERIFIED] Docker：当前环境未安装或不可用，仅保留配置。")
    print("[NOT_VERIFIED] Linux 服务器部署：本机为 Windows，需在目标机验证。")
    print("[NOT_VERIFIED] GitHub Actions：尚未推送仓库，需推送后查看真实运行结果。")

    print("=" * 68)
    if failures:
        print(f"发布验收失败：{failures} 项核心检查未通过。")
        return 1
    print("发布验收核心检查全部通过；未执行项已标记 NOT_VERIFIED。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

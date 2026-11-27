"""自动化 CLI 脚本共用的上下文构建（仪器 -> 测试台 -> 执行器 -> 存储）。

只负责组装，不包含业务判定；三个脚本共用同一套配置路径与数据来源声明，
避免不同入口产生不同的实验条件。
"""

from __future__ import annotations

import platform
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from analysis.performance_analyzer import PerformanceAnalyzer
from bench.virtual_test_bench import VirtualTestBench
from core.paths import CONFIG_DIR, DATABASE_PATH, RESULTS_DIR
from engine.test_runner import TestRunner
from instruments.manager import InstrumentManager
from models.virtual_dut import VirtualDUT
from storage.result_store import ResultStore
from storage.sqlite_store import SQLiteStore

INSTRUMENT_CONFIG = CONFIG_DIR / "instruments.yaml"
DUT_CONFIG = CONFIG_DIR / "dut_config.yaml"
LIMITS_CONFIG = CONFIG_DIR / "performance_limits.yaml"
DEFAULT_CASES = CONFIG_DIR / "test_cases.yaml"
DEFAULT_SUITES = CONFIG_DIR / "test_suites.yaml"
DEFAULT_RESULTS = RESULTS_DIR / "automation"
DEFAULT_DB = DATABASE_PATH


@dataclass
class AutomationContext:
    """一次自动化运行所需的全部对象。"""

    manager: InstrumentManager
    bench: VirtualTestBench
    analyzer: PerformanceAnalyzer
    runner: TestRunner
    result_store: ResultStore
    sqlite_store: SQLiteStore


def _environment() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "data_mode": "SIMULATION",
        "instrument_backend": "pyvisa-sim",
        "dut_model": "virtual_dut.behavioral_model",
    }


def _snapshots(cases_path: Path) -> dict[str, Path]:
    return {
        "test_cases_snapshot.yaml": cases_path,
        "dut_config_snapshot.yaml": DUT_CONFIG,
        "limits_snapshot.yaml": LIMITS_CONFIG,
    }


@contextmanager
def build_context(
    results_root: str | Path | None = None,
    db_path: str | Path | None = None,
    cases_path: str | Path | None = None,
) -> Iterator[AutomationContext]:
    """打开虚拟仪器并组装执行器；退出时统一安全关断。"""
    with InstrumentManager(INSTRUMENT_CONFIG) as manager:
        dut = VirtualDUT.from_yaml(DUT_CONFIG)
        bench = VirtualTestBench(manager, dut)
        analyzer = PerformanceAnalyzer(LIMITS_CONFIG)
        runner = TestRunner(manager, bench, analyzer)
        store = ResultStore(
            results_root or DEFAULT_RESULTS,
            snapshot_files=_snapshots(Path(cases_path or DEFAULT_CASES)),
            environment=_environment(),
        )
        sqlite_store = SQLiteStore(db_path or DEFAULT_DB)
        yield AutomationContext(
            manager=manager,
            bench=bench,
            analyzer=analyzer,
            runner=runner,
            result_store=store,
            sqlite_store=sqlite_store,
        )

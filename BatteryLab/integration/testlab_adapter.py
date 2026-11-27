"""TestLab 只读适配：真实调用其工程限值判定模块。

历史事实（本阶段实测）：TestLab 没有面向外部系统的测量导入接口，但有可
直接调用的 ``engine.result_judge.judge`` / ``judge_voltage``。本适配层因此采用
"BatteryLab 数据格式转换 + 只读调用真实判定函数"的方式，而不是另写一个判定
函数冒充 TestLab。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from integration.environment_adapter import hash_tree, run_python_script
from integration.measurement_exchange import SystemMeasurement

BRIDGE_SCRIPT = Path(__file__).resolve().parent / "testlab_bridge.py"


class TestLabAdapterError(RuntimeError):
    """TestLab 只读访问失败。"""


def inspect_testlab_api(root: str | Path) -> dict[str, Any]:
    base = Path(root)
    if not base.is_dir():
        raise TestLabAdapterError(f"TestLab 目录不存在: {base}")
    judge = base / "engine" / "result_judge.py"
    cases = base / "configs" / "test_cases.yaml"
    version = base / "VERSION"
    text = judge.read_text(encoding="utf-8") if judge.is_file() else ""
    return {
        "root": str(base),
        "version": version.read_text(encoding="utf-8").strip() if version.is_file() else None,
        "has_result_judge": judge.is_file(),
        "judge_functions": [name for name in ("judge", "judge_voltage", "judge_range", "aggregate_status") if f"def {name}(" in text],
        "has_external_measurement_import": any(
            token in text.lower() for token in ("import_measurement", "external_measurement", "load_measurements")
        ),
        "test_case_config": cases.is_file(),
        "source_file_count": len(hash_tree(base, extensions=(".py",))),
        "integration_mode": "read_only_call_of_real_judge_function",
        "note": "TestLab 无外部测量导入接口；通过只读导入 engine.result_judge 完成真实判定调用",
    }


def judge_measurements(
    root: str | Path,
    measurements: Iterable[SystemMeasurement],
    *,
    limits: dict[str, dict[str, float]],
    output_directory: str | Path,
    timeout_s: float = 120,
) -> dict[str, Any]:
    """把 BatteryLab 测量转换为 TestLab 判定输入并真实调用其判定函数。"""
    base = Path(root)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"measurements": []}
    for item in measurements:
        limit = limits.get(item.metric, {})
        payload["measurements"].append(
            {
                "metric": item.metric,
                "value": item.value,
                "unit": item.unit,
                "minimum": limit.get("min"),
                "maximum": limit.get("max"),
            }
        )
    input_path = directory / "testlab_judge_input.json"
    output_path = directory / "actual_test_results.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    execution = run_python_script(
        "kaifa",
        BRIDGE_SCRIPT,
        ["--project-root", str(base.resolve()), "--input", str(input_path.resolve()),
         "--output", str(output_path.resolve())],
        working_directory=directory,
        timeout_s=timeout_s,
    )
    actual = None
    if output_path.is_file():
        actual = json.loads(output_path.read_text(encoding="utf-8"))
    return {"execution": execution, "actual_test_results": actual}


__all__ = ["TestLabAdapterError", "inspect_testlab_api", "judge_measurements"]

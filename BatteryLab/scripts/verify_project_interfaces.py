"""任务 7：核验三项目真实接口、版本、核心文件与只读哈希。

输出：

- ``cross_project_manifest.json``：三项目真实状态；
- ``cross_project_interface_policy.json``：本阶段允许的调用方式与禁止项；
- ``source_snapshot_before.json``：运行前源码哈希快照（用于事后证明未修改）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integration.powerlab_adapter import load_powerlab_parameters, powerlab_source_snapshot  # noqa: E402
from integration.project_registry import inspect_all, load_project_paths  # noqa: E402
from integration.testlab_adapter import inspect_testlab_api  # noqa: E402
from scripts.stage9_common import STAGE9_RESULTS, new_run_dir, read_json, write_json  # noqa: E402
from validation.cross_project_regression import snapshot_projects  # noqa: E402


def build_manifest() -> dict:
    return inspect_all()


def main() -> int:
    parser = argparse.ArgumentParser(description="核验三项目真实接口")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    run_id, directory = (
        (Path(args.run_dir).name, Path(args.run_dir))
        if args.run_dir
        else new_run_dir(STAGE9_RESULTS / "project_interfaces", "verify_interfaces")
    )
    directory.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest()
    projects = load_project_paths()
    testlab = inspect_testlab_api(projects["testlab"]["root"]) if projects["testlab"]["root"] and Path(projects["testlab"]["root"]).is_dir() else {"status": "MISSING"}
    powerlab = (
        load_powerlab_parameters(projects["powerlab"]["root"])
        if Path(projects["powerlab"]["root"]).is_dir()
        else {"status": "MISSING"}
    )
    powerlab_snapshot = (
        powerlab_source_snapshot(projects["powerlab"]["root"])
        if Path(projects["powerlab"]["root"]).is_dir()
        else {"status": "MISSING"}
    )
    before = snapshot_projects()

    policy = {
        "run_id": run_id,
        "allowed": [
            "只读读取 TestLab / PowerLab 源码、配置与历史结果",
            "通过子进程在 kaifa_power 环境调用 PowerLab 闭环构建器（不写入 PowerLab）",
            "通过子进程在 kaifa 环境只读导入 TestLab engine.result_judge",
            "在独立临时目录生成本阶段结果",
        ],
        "forbidden": [
            "修改 TestLab 或 PowerLab 源码、配置或历史结果",
            "直接向其他项目 results 目录写入",
            "在未验证的记录上标记 PASS",
        ],
        "measurement_format": "schemas/system_measurements_v1.schema.json",
        "blocked_reasons": [],
    }
    missing_projects = [name for name, record in manifest["projects"].items() if not record["exists"]]
    if missing_projects:
        policy["blocked_reasons"].append(f"缺失项目目录: {missing_projects}")
    missing_entries = {
        name: record["key_files"]["missing"]
        for name, record in manifest["projects"].items()
        if record["key_files"]["missing"]
    }
    if missing_entries:
        policy["blocked_reasons"].append(f"核心文件缺失: {missing_entries}")
    if not testlab.get("has_result_judge"):
        policy["blocked_reasons"].append("TestLab 缺少 engine/result_judge.py")
    if not powerlab.get("power_stage"):
        policy["blocked_reasons"].append("PowerLab 配置缺失")

    payload = {
        "run_id": run_id,
        "status": "PASS" if not policy["blocked_reasons"] else "BLOCKED",
        "manifest": manifest,
        "testlab_api": testlab,
        "powerlab_parameters": powerlab,
        "powerlab_source": powerlab_snapshot,
    }
    write_json(directory / "cross_project_manifest.json", payload)
    write_json(directory / "cross_project_interface_policy.json", policy)
    write_json(directory / "source_snapshot_before.json", before)
    write_json(directory / "execution_summary.json", {
        "run_id": run_id,
        "status": payload["status"],
        "projects_present": manifest["all_present"],
        "key_files_present": manifest["all_key_files_present"],
        "blocked_reasons": policy["blocked_reasons"],
    })

    print(json.dumps({"run_id": run_id, "status": payload["status"],
                      "blocked_reasons": policy["blocked_reasons"]}, ensure_ascii=False))
    if args.json_out:
        write_json(args.json_out, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

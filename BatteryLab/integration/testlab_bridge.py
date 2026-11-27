"""TestLab 只读桥接脚本（在 kaifa 环境执行）。

真实导入 TestLab ``engine.result_judge`` 并调用其判定函数；不修改 TestLab
任何文件，也不向 TestLab 目录写日志。结果写回 BatteryLab 运行目录。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    sys.path.insert(0, str(root))

    import hashlib

    judge_module = root / "engine" / "result_judge.py"
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    try:
        from engine.result_judge import judge
        import engine.result_judge as module
    except Exception as exc:  # noqa: BLE001 - 保留真实导入失败
        Path(args.output).write_text(
            json.dumps(
                {
                    "status": "IMPORT_FAILED",
                    "error": f"{type(exc).__name__}: {exc}",
                    "project_root": str(root),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(json.dumps({"status": "IMPORT_FAILED"}))
        return 2

    results = []
    for item in payload.get("measurements", []):
        value = item.get("value")
        minimum = item.get("minimum")
        maximum = item.get("maximum")
        record = {
            "metric": item.get("metric"),
            "value": value,
            "minimum": minimum,
            "maximum": maximum,
            "testlab_status": None,
            "testlab_detail": None,
        }
        if value is None:
            record["testlab_status"] = "NOT_APPLICABLE"
            record["testlab_detail"] = "无有效测量值，TestLab 不判定"
        else:
            try:
                verdict = judge(float(value), minimum=minimum, maximum=maximum)
                record["testlab_status"] = "PASS" if verdict.passed else "FAIL"
                record["testlab_detail"] = verdict.detail
            except Exception as exc:  # noqa: BLE001
                record["testlab_status"] = "ERROR"
                record["testlab_detail"] = f"{type(exc).__name__}: {exc}"
        results.append(record)

    output = {
        "status": "JUDGED",
        "project_root": str(root),
        "testlab_judge_source": str(judge_module),
        "testlab_judge_sha256": hashlib.sha256(judge_module.read_bytes()).hexdigest(),
        "testlab_judge_file": getattr(module, "__file__", None),
        "results": results,
        "passed": sum(1 for item in results if item["testlab_status"] == "PASS"),
        "failed": sum(1 for item in results if item["testlab_status"] == "FAIL"),
        "errors": sum(1 for item in results if item["testlab_status"] == "ERROR"),
        "not_applicable": sum(1 for item in results if item["testlab_status"] == "NOT_APPLICABLE"),
    }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "JUDGED", "judged": len(results)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""真实 Web 任务冒烟演示（第九阶段 Task 17）。

通过任务管理器提交一个真实 SPICE 任务并等待结果，用于验收记录。

用法：
    conda run -n kaifa_power python -m scripts.web_smoke_demo
    conda run -n kaifa_power python -m scripts.web_smoke_demo --model nonideal_buck --end-ms 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jobs.manager import JobManager  # noqa: E402
from jobs.registry import MODEL_SPECS  # noqa: E402
from storage.run_index import build_index, save_index  # noqa: E402


def _request(model: str, end_ms: float) -> dict:
    values = {field.name: field.default for field in MODEL_SPECS[model].fields}
    values["model"] = model
    if "end_time_s" in values:
        values["end_time_s"] = end_ms
    if model == "nonideal_buck":
        values["variant"] = "E"
        values["step_time_s"] = 200.0
        values["max_step_time_s"] = 100.0
        values["end_time_s"] = max(0.5, min(end_ms, 2.0))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="PowerLab web job smoke demo")
    parser.add_argument("--model", default="voltage_divider", choices=sorted(MODEL_SPECS))
    parser.add_argument("--end-ms", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    manager = JobManager()
    record = manager.submit("circuit_simulation", _request(args.model, args.end_ms))
    print(f"submitted {record.job_id} ({args.model})")
    done = manager.wait_for(record.job_id, timeout_s=args.timeout)
    print(f"status={done.status.value} runs={done.result_run_ids} error={done.error_message}")
    index = build_index()
    save_index(index)
    print(f"indexed runs={len(index.entries)}")
    summary = {
        "job_id": done.job_id,
        "model": args.model,
        "status": done.status.value,
        "result_run_ids": done.result_run_ids,
        "solver_calls": done.solver_calls,
        "error_message": done.error_message,
        "index_total": len(index.entries),
    }
    target = PROJECT_ROOT / "results" / "stage9" / "web_smoke_demo.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary -> {target}")
    return 0 if done.status.value == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

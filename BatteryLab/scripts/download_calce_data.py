"""Task 12：下载 CALCE INR18650-20R 官方公开数据（25℃ 优先）。

默认预算 500MB；已存在且 SHA256 一致的文件不重复下载。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from datasets.catalog import MANIFEST_CSV, MANIFEST_JSON
from datasets.downloader import download_datasets
from storage.result_store import RunDirectory


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 CALCE INR18650-20R 公开数据")
    parser.add_argument("--budget-mb", type=float, default=None)
    parser.add_argument("--force", action="store_true", help="强制重新下载")
    args = parser.parse_args()

    config = yaml.safe_load((PROJECT_ROOT / "configs" / "dataset_config.yaml").read_text(encoding="utf-8"))
    budget = args.budget_mb if args.budget_mb is not None else float(config["download"]["budget_mb"])

    result = download_datasets(budget_mb=budget, force=args.force)
    run = RunDirectory("calce")
    run.write_metadata({"script": "scripts/download_calce_data.py", "provider": "CALCE", "budget_mb": budget})
    run.write_summary(result)
    run.log(f"下载完成: {result['downloaded']} 个新文件, {result['already_present']} 个已存在, {result['failed']} 个失败")
    run.flush_log()

    report = {key: value for key, value in result.items() if key != "entries"}
    report.update(
        {
            "run_id": run.run_id,
            "run_path": str(run.path),
            "manifest_json": str(MANIFEST_JSON),
            "manifest_csv": str(MANIFEST_CSV),
            "entries": result["entries"],
        }
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

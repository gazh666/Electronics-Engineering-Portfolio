"""Task 13–16：EDA 状态核查入口。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.hardening_eda
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hardening.common import new_run, write_json  # noqa: E402
from hardening.eda_status import build_status, markdown  # noqa: E402


def main() -> int:
    run = new_run("eda")
    status = build_status()
    write_json(run / "eda_status.json", status)
    (run / "eda_status.md").write_text(markdown(status), encoding="utf-8")
    print(json.dumps({
        "run_id": run.name,
        "status": status["status"],
        "kicad_available": status["kicad"]["available"],
        "stage8_counts": status["baseline"].get("validation_summary", {}).get("status_counts"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

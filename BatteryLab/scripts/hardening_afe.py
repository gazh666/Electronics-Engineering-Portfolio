"""Task 4：AFE 最坏情况误差预算与器件优化复验入口。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.hardening_afe
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hardening.afe_optimization import run  # noqa: E402

if __name__ == "__main__":
    summary = run()
    print(json.dumps({
        "run_id": summary["run_id"],
        "baseline_voltage_mv": summary["baseline"]["voltage_worst_case_mv"],
        "baseline_current_ma": summary["baseline"]["current_worst_case_ma"],
        "optimized": summary["optimized"]["design"],
        "optimized_voltage_mv": summary["optimized"]["voltage_worst_case_mv"],
        "optimized_current_ma": summary["optimized"]["current_worst_case_ma"],
        "voltage_target_met": summary["optimized"]["voltage_target_met"],
        "current_target_met": summary["optimized"]["current_target_met"],
    }, ensure_ascii=False))
    raise SystemExit(0)

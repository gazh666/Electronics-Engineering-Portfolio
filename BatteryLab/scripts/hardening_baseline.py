"""Task 1：执行补强基线快照。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.hardening_baseline
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hardening.baseline_audit import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

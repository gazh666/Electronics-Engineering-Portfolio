"""环境验证入口。

判定标准：
1. 依赖版本可读取；
2. ngspice 后端能完成一次真实分压求解；
3. 结果目录可写。

仅 import PySpice 不算通过。
"""

from __future__ import annotations

import json
import sys

from simulations.artifacts import RESULTS_ROOT, create_run_dir, write_json
from simulations.environment import (
    EnvironmentError,
    check_results_writable,
    collect_environment,
    verify_backend,
)


def main() -> int:
    report: dict[str, object] = {"environment": collect_environment()}
    try:
        report["backend_probe"] = verify_backend()
        report["results_write_probe"] = str(check_results_writable(RESULTS_ROOT))
        report["status"] = "OK"
    except (EnvironmentError, OSError) as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    run_dir = create_run_dir("environment", RESULTS_ROOT)
    write_json(run_dir / "environment.json", report)
    report["report_path"] = str(run_dir / "environment.json")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

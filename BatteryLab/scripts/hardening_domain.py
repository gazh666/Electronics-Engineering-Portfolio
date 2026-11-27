"""Task 11/12：有效域审计与 SOH/LLC 分级入口。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.hardening_domain
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hardening.common import new_run, status_counts, write_csv, write_json  # noqa: E402
from hardening.domain_audit import (  # noqa: E402
    llc_classification,
    operating_domain,
    pack_soc_classification,
    soc_method_classification,
    soh_classification,
    temperature_availability,
)


def main() -> int:
    run = new_run("domain")
    domain = operating_domain()
    soh = soh_classification()
    llc = llc_classification()
    soc = soc_method_classification()
    pack = pack_soc_classification()
    temperature = temperature_availability()
    write_csv(run / "operating_domain.csv", domain)
    write_csv(run / "soh_classification.csv", soh)
    write_csv(run / "llc_classification.csv", llc)
    write_csv(run / "soc_method_classification.csv", soc)
    write_csv(run / "pack_soc_classification.csv", pack)
    write_csv(run / "temperature_availability.csv", temperature)
    summary = {
        "run_id": run.name,
        "operating_domain": domain,
        "domain_status_counts": status_counts(row["status"] for row in domain),
        "soh": soh,
        "soh_status_counts": status_counts(row["evidence_level"] for row in soh),
        "llc": llc,
        "soc_methods": soc,
        "pack_soc": pack,
        "temperature": temperature,
        "notes": [
            "外推工况必须标记 OUTSIDE_IDENTIFIED_WINDOW，不得作为已验证结果。",
            "容量衰减与内阻增长是电池健康状态研究结果，不是本项目降低真实老化速度的成果。",
            "合成长序列与公开实测数据严格分开。",
        ],
    }
    write_json(run / "domain_summary.json", summary)
    print(json.dumps({
        "run_id": run.name,
        "domain": summary["domain_status_counts"],
        "soh": summary["soh_status_counts"],
        "llc_rows": len(llc),
        "soc_methods": [row["method"] for row in soc],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""真实老化数据加载与可用性核查（Task 23）。

本阶段 `data/raw/` 只有 CALCE INR18650-20R 的 25℃ 初始容量、低电流 OCV、
DST/FUDS/US06/BJDST 动态工况，**没有**连续循环老化数据，也没有 NASA 老化
电芯。因此：

- 真实容量衰减 / 真实 SOH / 真实内阻老化验证统一标记 ``NOT_VERIFIED``；
- 只允许用合成循环数据完成解析、积分与容量计算的数学单元测试；
- 合成数据必须标记 ``source_type = synthetic_truth``，不得冒充公开实验。

若后续下载 NASA 老化数据（B0005 等仅为候选名，以官方文件为准），必须建立
独立数据配置，**不得把 NASA 电芯称为 CALCE INR18650-20R**。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

AGING_KEYWORDS = ("aging", "aged", "cycle", "soh", "calendar", "rpt")

OFFICIAL_SOURCES = (
    {
        "name": "CALCE Battery Data",
        "url": "https://calce.umd.edu/battery-data",
        "note": "本阶段已获数据为初始容量/OCV/动态工况，未含连续老化循环。",
    },
    {
        "name": "NASA Li-ion Battery Aging Datasets",
        "url": "https://data.nasa.gov/dataset/li-ion-battery-aging-datasets",
        "note": "未下载。若使用需独立配置，电芯型号与 CALCE 不同。",
    },
    {
        "name": "NASA PCoE Data Set Repository",
        "url": "https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/",
        "note": "入口备用，未下载。",
    },
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_aging_datasets(raw_dir: str | Path | None = None) -> dict[str, Any]:
    """扫描 data/raw，判断是否存在可用的真实老化数据。"""
    base = Path(raw_dir) if raw_dir is not None else RAW_DIR
    files = sorted(path for path in base.glob("*") if path.is_file()) if base.exists() else []
    candidates = [
        path
        for path in files
        if any(keyword in path.name.lower() for keyword in AGING_KEYWORDS)
    ]
    inventory = [
        {
            "file_name": path.name,
            "size_bytes": int(path.stat().st_size),
            "sha256": file_sha256(path),
            "aging_candidate": bool(path in candidates),
        }
        for path in files
    ]
    status = "AVAILABLE" if candidates else "NOT_VERIFIED"
    return {
        "status": status,
        "reason": (
            "检测到疑似老化数据文件，需人工核对数据结构后方可使用。"
            if candidates
            else "data/raw 仅含初始容量/OCV/动态工况，未发现连续老化循环文件。"
        ),
        "raw_dir": str(base),
        "file_count": len(files),
        "aging_candidate_count": len(candidates),
        "aging_candidates": [path.name for path in candidates],
        "inventory": inventory,
        "official_sources": list(OFFICIAL_SOURCES),
        "real_soh_validation": "NOT_VERIFIED",
    }


def synthetic_aging_cycles(
    *,
    cell_id: str = "SYNTHETIC_SP2_LIKE",
    initial_capacity_ah: float = 2.0,
    fade_per_cycle_ah: float = 0.002,
    cycle_count: int = 100,
    temperature_c: float = 25.0,
) -> list[dict[str, Any]]:
    """生成合成老化循环表，仅用于算法数学验证（不是真实实验）。"""
    if initial_capacity_ah <= 0.0 or fade_per_cycle_ah < 0.0 or cycle_count <= 0:
        raise ValueError("Invalid synthetic aging parameter")
    rows: list[dict[str, Any]] = []
    for cycle in range(1, cycle_count + 1):
        capacity = max(initial_capacity_ah - fade_per_cycle_ah * (cycle - 1), 0.0)
        rows.append(
            {
                "cell_id": cell_id,
                "cycle_index": int(cycle),
                "discharge_capacity_ah": float(capacity),
                "reference_capacity_ah": float(initial_capacity_ah),
                "temperature_c": float(temperature_c),
                "cutoff_voltage_v": 2.5,
                "recorded_capacity_ah": float(capacity),
                "integrated_capacity_ah": float(capacity),
                "data_quality_status": "SYNTHETIC_TRUTH",
            }
        )
    return rows


def build_manifest(raw_dir: str | Path | None = None) -> dict[str, Any]:
    """生成可落盘的 aging_data_manifest.json 内容。"""
    scan = scan_aging_datasets(raw_dir)
    return {
        "source_type": "public_experimental_data",
        "available_real_aging_data": scan["status"] == "AVAILABLE",
        "status": scan["status"],
        "reason": scan["reason"],
        "details": scan,
        "synthetic_validation_only": True,
        "citation_required": True,
    }

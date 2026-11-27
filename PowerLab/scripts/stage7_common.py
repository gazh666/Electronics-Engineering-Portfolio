"""第七阶段脚本共用输出工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.frequency_response import sanitize_for_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = PROJECT_ROOT / "results" / "stage7" / "demos"


def ensure_demo_dir() -> Path:
    DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    return DEMO_ROOT


def save_json(name: str, payload: dict[str, Any]) -> Path:
    path = ensure_demo_dir() / name
    path.write_text(
        json.dumps(sanitize_for_json(payload), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return path


def save_csv(name: str, frame: pd.DataFrame) -> Path:
    path = ensure_demo_dir() / name
    frame.to_csv(path, index=False, encoding="utf-8", float_format="%.9g")
    return path

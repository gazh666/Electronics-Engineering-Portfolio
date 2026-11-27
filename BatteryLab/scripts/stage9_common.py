"""第九阶段脚本共用工具：运行目录、JSON 输出与限制值读取。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from battery_models.parameters import PROJECT_ROOT, load_yaml

STAGE9_RESULTS = PROJECT_ROOT / "results" / "stage9"


def new_run_dir(root: str | Path, prefix: str, *, run_id: str | None = None) -> tuple[str, Path]:
    base = Path(root)
    resolved = run_id or f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    path = base / resolved
    path.mkdir(parents=True, exist_ok=False)
    (path / "run_id.txt").write_text(resolved, encoding="utf-8")
    return resolved, path


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return target


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validation_limits() -> dict[str, Any]:
    return load_yaml(PROJECT_ROOT / "configs" / "system_validation.yaml")


def emit(args: Any, payload: dict[str, Any], default_name: str) -> None:
    """可选写出 `--json-out`，同时打印关键状态。"""
    if getattr(args, "json_out", None):
        write_json(args.json_out, payload)
    status = payload.get("status") or payload.get("summary", {}).get("status")
    print(json.dumps({"payload": default_name, "status": status}, ensure_ascii=False))


__all__ = [
    "STAGE9_RESULTS",
    "emit",
    "new_run_dir",
    "read_json",
    "validation_limits",
    "write_json",
]

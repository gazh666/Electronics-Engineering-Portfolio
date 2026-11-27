"""故障与重试事件日志（JSONL）。

约束
----
- 每个事件立即追加并刷新，测试中断也能保留已发生的事件；
- 事件编号全局唯一，时间为带时区的 ISO 格式；
- NaN / ±Infinity 写成明确字符串，保证输出是合法 JSON；
- 日志写入失败只记录并报告，**绝不阻断**仪器清理与后续安全操作；
- 不记录 API Key、密码等敏感信息（本模块只接收结构化事件字段）。
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import is_dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

__all__ = [
    "EventType",
    "FaultLogger",
    "new_event",
    "normalize_event",
    "sanitize_event_value",
]


class EventType(str, Enum):
    """可靠性事件类型。"""

    #: 阻止 pytest 把本枚举当作测试类收集
    __test__ = False

    FAULT_INJECTED = "FAULT_INJECTED"
    ATTEMPT_FAILED = "ATTEMPT_FAILED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    RECOVERED = "RECOVERED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    TEST_ABORTED = "TEST_ABORTED"
    CLEANUP_STARTED = "CLEANUP_STARTED"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    CLEANUP_COMPLETED = "CLEANUP_COMPLETED"


#: 事件允许的核心字段（缺失字段会被补为 None）
EVENT_FIELDS = (
    "event_id",
    "run_id",
    "case_id",
    "scenario_id",
    "timestamp",
    "event_type",
    "fault_type",
    "target",
    "device_id",
    "operation",
    "operation_id",
    "attempt_number",
    "retry_number",
    "error_category",
    "exception_type",
    "message",
    "original_value",
    "injected_value",
    "cleanup_status",
    "details",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sanitize_event_value(value: Any) -> Any:
    """递归把事件值转换为可 JSON 序列化的结构。"""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, Mapping):
        return {str(key): sanitize_event_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_event_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return sanitize_event_value(asdict(value))
    return value


def normalize_event(
    event: Mapping[str, Any],
    *,
    run_id: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """补齐标准字段并归一化事件类型。"""
    payload: dict[str, Any] = {field: None for field in EVENT_FIELDS}
    payload.update(dict(event))
    payload["event_id"] = str(payload.get("event_id") or uuid.uuid4().hex)
    payload["timestamp"] = str(payload.get("timestamp") or _now_iso())

    event_type = payload.get("event_type")
    if isinstance(event_type, Enum):
        payload["event_type"] = event_type.value
    elif not isinstance(event_type, str) or not event_type.strip():
        raise ValueError(f"事件缺少合法 event_type: {event_type!r}")

    if payload.get("run_id") is None:
        payload["run_id"] = run_id
    if payload.get("case_id") is None:
        payload["case_id"] = case_id
    if not isinstance(payload.get("details"), dict):
        payload["details"] = {}
    return payload


def new_event(event_type: EventType | str, **fields: Any) -> dict[str, Any]:
    """构造一条标准事件（尚未写入文件）。"""
    value = getattr(event_type, "value", event_type)
    payload = {"event_type": value}
    payload.update(fields)
    return normalize_event(payload)


class FaultLogger:
    """把事件追加写入 JSONL 文件；同时保留内存副本供统计使用。"""

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        run_id: str | None = None,
        default_case_id: str | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.run_id = run_id
        self.default_case_id = default_case_id
        self.on_error = on_error
        self.events: list[dict[str, Any]] = []
        self.write_errors: list[str] = []
        self._closed = False

        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # 运行开始前清空本次文件，避免追加到旧实验
            self.path.write_text("", encoding="utf-8")

    # --- 写入 ---

    def emit(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """记录并立即落盘；写入失败不抛出。"""
        payload = normalize_event(
            event,
            run_id=self.run_id,
            case_id=self.default_case_id,
        )
        self.events.append(payload)
        if self.path is None or self._closed:
            return payload

        try:
            line = json.dumps(
                sanitize_event_value(payload),
                ensure_ascii=False,
                allow_nan=False,
            )
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
                file.flush()
        except Exception as exc:  # 日志失败不得阻断清理
            message = f"故障事件日志写入失败: {type(exc).__name__}: {exc}"
            self.write_errors.append(message)
            if self.on_error is not None:
                try:
                    self.on_error(message)
                except Exception:
                    pass
        return payload

    def flush(self) -> None:
        """保留接口：每次 emit 已刷新，这里仅用于显式语义。"""

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> "FaultLogger":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    # --- 查询 ---

    def event_types(self) -> list[str]:
        return [str(event.get("event_type")) for event in self.events]

    @property
    def has_write_errors(self) -> bool:
        return bool(self.write_errors)

"""第五阶段公共工具：配置、3S 电芯组、PASS/FAIL 登记与结果落盘。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from battery_models.battery_pack import PackCellModel, SeriesBatteryPack, build_inconsistent_pack
from battery_models.ocv_model import load_ocv_reference
from battery_models.parameters import load_ecm_models
from protection.limits import ProtectionLimits, load_limits

STAGE = "stage5"
MODEL_KEY = "first_order_rc"  # 与第三阶段冻结模型一致：R0 + 一阶 RC


@dataclass(frozen=True)
class Check:
    name: str
    measured: float | None
    limit: float | None
    unit: str
    status: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "measured": self.measured,
            "limit": self.limit,
            "unit": self.unit,
            "status": self.status,
            "note": self.note,
        }


def check_at_most(name: str, measured: float, limit: float, unit: str, note: str = "") -> Check:
    status = "PASS" if measured <= limit else "FAIL"
    return Check(name, measured, limit, unit, status, note)


def check_at_least(name: str, measured: float, limit: float, unit: str, note: str = "") -> Check:
    status = "PASS" if measured >= limit else "FAIL"
    return Check(name, measured, limit, unit, status, note)


def check_within(name: str, measured: float, limit: float, unit: str, note: str = "") -> Check:
    status = "PASS" if abs(measured) <= limit else "FAIL"
    return Check(name, measured, limit, unit, status, note)


def check_true(name: str, condition: bool, note: str = "") -> Check:
    return Check(name, 1.0 if condition else 0.0, 1.0, "bool", "PASS" if condition else "FAIL", note)


def summarize_checks(checks: Sequence[Check]) -> dict[str, Any]:
    passed = sum(1 for item in checks if item.status == "PASS")
    failed = sum(1 for item in checks if item.status == "FAIL")
    return {
        "stage": STAGE,
        "checks": [item.to_dict() for item in checks],
        "passed": passed,
        "failed": failed,
        "total": len(checks),
        "status": "PASS" if failed == 0 else "FAIL",
    }


def make_pack(
    socs: Sequence[float],
    *,
    capacities_ah: Sequence[float] | None = None,
    r0_ohm: Sequence[float] | None = None,
) -> SeriesBatteryPack:
    definition = load_ecm_models()[MODEL_KEY]
    ocv = load_ocv_reference()
    return build_inconsistent_pack(
        definition, ocv, socs=socs, capacities_ah=capacities_ah, r0_ohm=r0_ohm
    )


def pack_cells(socs: Sequence[float], **kwargs: Any) -> list[PackCellModel]:
    return list(make_pack(socs, **kwargs).cells)


def stage5_limits() -> ProtectionLimits:
    return load_limits()


def cell_soc_for_voltage(target_voltage_v: float, definition=None, ocv=None) -> float:
    """在冻结 OCV 表上反解 SOC，用于把目标电压映射成初始 SOC。"""
    definition = definition or load_ecm_models()[MODEL_KEY]
    ocv = ocv or load_ocv_reference()
    low, high = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (low + high)
        if float(ocv.voltage(mid)) < target_voltage_v:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)

"""第七阶段电池健康（SOH）评估包。

严格区分容量型 SOH 与内阻健康指标，不构造无依据的"综合 SOH"。
真实老化数据不可用时统一标记 NOT_VERIFIED。
"""

from health.aging_data_loader import (
    build_manifest,
    scan_aging_datasets,
    synthetic_aging_cycles,
)
from health.capacity_soh import CapacityHealth, calculate_capacity_soh
from health.capacity_update import (
    CapacityUpdater,
    update_capacity_estimate,
)
from health.cycle_analysis import (
    build_cycle_table,
    integrate_discharge_capacity,
    summarize_cycles,
)
from health.resistance_health import (
    ResistanceCondition,
    compare_resistance_conditions,
    pulse_resistance_ohm,
    resistance_growth_percent,
)

__all__ = [
    "CapacityHealth",
    "calculate_capacity_soh",
    "resistance_growth_percent",
    "pulse_resistance_ohm",
    "ResistanceCondition",
    "compare_resistance_conditions",
    "build_manifest",
    "scan_aging_datasets",
    "synthetic_aging_cycles",
    "integrate_discharge_capacity",
    "build_cycle_table",
    "summarize_cycles",
    "update_capacity_estimate",
    "CapacityUpdater",
]

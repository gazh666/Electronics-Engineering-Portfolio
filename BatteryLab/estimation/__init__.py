"""第七阶段 SOC / SOH 状态估计包。

约定继承前六阶段：时间 s、电流 A、容量 Ah、SOC 0-1。
电流方向统一为放电为正、充电为负（与 ECM 模型一致）。
"""

from estimation.coulomb_counter import CoulombCounter, SOCUpdate
from estimation.ecm_observer import ECMObserver, ObserverRCBranch, ObserverResult
from estimation.estimation_runner import (
    replay_coulomb_counting,
    replay_observer,
    replay_raw_ocv,
    replay_rest_corrected,
    summarize_replay,
)
from estimation.models import MeasurementSample, SOCEstimate
from estimation.ocv_estimator import OCVEstimate, OCVSOCTable
from estimation.pack_soc_estimator import (
    PackSOCEstimator,
    calculate_cell_currents,
    summarize_pack_soc,
)
from estimation.rest_detector import RestDetector
from estimation.soc_correction import (
    CorrectionResult,
    SOCCorrectionScheduler,
    correct_soc_from_ocv,
)

__all__ = [
    "CoulombCounter",
    "SOCUpdate",
    "MeasurementSample",
    "SOCEstimate",
    "OCVEstimate",
    "OCVSOCTable",
    "RestDetector",
    "CorrectionResult",
    "SOCCorrectionScheduler",
    "correct_soc_from_ocv",
    "ECMObserver",
    "ObserverRCBranch",
    "ObserverResult",
    "PackSOCEstimator",
    "calculate_cell_currents",
    "summarize_pack_soc",
    "replay_coulomb_counting",
    "replay_raw_ocv",
    "replay_rest_corrected",
    "replay_observer",
    "summarize_replay",
]

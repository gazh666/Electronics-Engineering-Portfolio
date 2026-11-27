"""估计器统一回放流程（Task 14）。

四个回放入口共享同一时间轴与数据质量规则：

- ``replay_coulomb_counting``：纯安时积分；
- ``replay_raw_ocv``：端电压直接查表（简化基准，带载时物理上不等价于 OCV）；
- ``replay_rest_corrected``：安时积分 + 静置 OCV 校正；
- ``replay_observer``：ECM 端电压残差反馈观测器。

统一规则（Task 7 / Task 14）：

1. 时间戳严格递增；
2. 单步间隔超过 ``maximum_gap_s`` 时标记 ``DATA_GAP``，**不跨越缺口积分**，
   该行 SOC 记为 ``None``（不可信），恢复后首个样本状态为 ``RESUMED_AFTER_GAP``；
3. 电流无效时不能积分，标记 ``INVALID_CURRENT``；
4. 电压无效时观测器只做电流预测，不做电压修正；
5. 不使用未来样本修正当前结果（所有回放均为单向前向）。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from estimation.ecm_observer import ECMObserver, ObserverResult
from estimation.models import MeasurementSample
from estimation.ocv_estimator import OCVSOCTable
from estimation.rest_detector import RestDetector
from estimation.soc_correction import SOCCorrectionScheduler


def _base_row(sample: MeasurementSample, soc: float | None, status: str) -> dict[str, Any]:
    return {
        "time_s": float(sample.time_s),
        "estimated_soc": soc,
        "predicted_soc": soc,
        "predicted_voltage_v": None,
        "voltage_residual_v": None,
        "correction": 0.0,
        "status": status,
        "trusted": soc is not None,
    }


def _gap_status(
    previous: MeasurementSample,
    current: MeasurementSample,
    maximum_gap_s: float,
) -> str | None:
    """返回不连续原因；连续则返回 None。"""
    dt = float(current.time_s) - float(previous.time_s)
    if dt <= 0.0:
        raise ValueError("Invalid time axis")
    if not previous.current_valid or not current.current_valid:
        return "INVALID_CURRENT"
    if not previous.voltage_valid or not current.voltage_valid:
        return None  # 电压无效由各回放器单独处理，电流仍可积分
    if dt > maximum_gap_s:
        return "DATA_GAP"
    return None


def replay_coulomb_counting(
    samples: Sequence[MeasurementSample],
    counter,
    maximum_gap_s: float = 2.0,
) -> list[dict[str, Any]]:
    """纯安时积分回放。"""
    sequence = list(samples)
    if len(sequence) < 2:
        raise ValueError("Insufficient samples")
    rows: list[dict[str, Any]] = [_base_row(sequence[0], counter.soc, "INITIAL")]
    previous = sequence[0]
    after_gap = False
    for current in sequence[1:]:
        dt = float(current.time_s) - float(previous.time_s)
        reason = _gap_status(previous, current, maximum_gap_s)
        if reason is not None:
            rows.append(_base_row(current, None, reason))
            after_gap = reason == "DATA_GAP"
            previous = current
            continue
        update = counter.step(previous.current_a, dt)
        status = update.status
        if after_gap:
            status = "RESUMED_AFTER_GAP"
            after_gap = False
        row = _base_row(current, update.soc, status)
        row["predicted_soc"] = update.raw_soc
        rows.append(row)
        previous = current
    return rows


def replay_raw_ocv(
    samples: Sequence[MeasurementSample],
    ocv_table: OCVSOCTable,
    maximum_gap_s: float = 2.0,
) -> list[dict[str, Any]]:
    """端电压直接 OCV 查表（不使用任何积分）。"""
    sequence = list(samples)
    if len(sequence) < 2:
        raise ValueError("Insufficient samples")
    rows: list[dict[str, Any]] = []
    first = sequence[0]
    if first.voltage_valid:
        initial_estimate = ocv_table.estimate(first.terminal_voltage_v)
        initial_row = _base_row(first, initial_estimate.soc, initial_estimate.status)
        initial_row["initial"] = True
    else:
        initial_row = _base_row(first, None, "INVALID_VOLTAGE")
    rows.append(initial_row)
    previous = sequence[0]
    for current in sequence[1:]:
        dt = float(current.time_s) - float(previous.time_s)
        if dt <= 0.0:
            raise ValueError("Invalid time axis")
        if not current.voltage_valid:
            rows.append(_base_row(current, None, "INVALID_VOLTAGE"))
            previous = current
            continue
        estimate = ocv_table.estimate(current.terminal_voltage_v)
        row = _base_row(current, estimate.soc, estimate.status)
        row["local_slope_v_per_soc"] = estimate.local_slope_v_per_soc
        rows.append(row)
        previous = current
    return rows


def replay_rest_corrected(
    samples: Sequence[MeasurementSample],
    counter,
    ocv_table: OCVSOCTable,
    rest_detector: RestDetector,
    scheduler: SOCCorrectionScheduler,
    maximum_gap_s: float = 2.0,
) -> list[dict[str, Any]]:
    """安时积分 + 静置 OCV 校正回放。"""
    sequence = list(samples)
    if len(sequence) < 2:
        raise ValueError("Insufficient samples")
    rows: list[dict[str, Any]] = [_base_row(sequence[0], counter.soc, "INITIAL")]
    previous = sequence[0]
    after_gap = False
    for current in sequence[1:]:
        dt = float(current.time_s) - float(previous.time_s)
        reason = _gap_status(previous, current, maximum_gap_s)
        if reason == "INVALID_CURRENT":
            rows.append(_base_row(current, None, reason))
            previous = current
            continue
        if reason == "DATA_GAP":
            rows.append(_base_row(current, None, reason))
            after_gap = True
            previous = current
            continue

        update = counter.step(previous.current_a, dt)
        status = update.status
        if after_gap:
            status = "RESUMED_AFTER_GAP"
            after_gap = False

        voltage_for_rest = current.terminal_voltage_v if current.voltage_valid else None
        eligible = rest_detector.update(
            time_s=current.time_s,
            current_a=current.current_a,
            valid=current.current_valid,
            voltage_v=voltage_for_rest,
            temperature_c=current.temperature_c,
        )

        ocv_soc: float | None = None
        ocv_status = "NOT_APPLICABLE"
        if eligible and current.voltage_valid:
            ocv_estimate = ocv_table.estimate(current.terminal_voltage_v)
            if ocv_estimate.status == "VALID":
                ocv_soc = ocv_estimate.soc
            ocv_status = ocv_estimate.status

        correction = scheduler.apply(
            time_s=current.time_s,
            predicted_soc=counter.soc,
            ocv_soc=ocv_soc,
            eligible=eligible and ocv_soc is not None,
            rest_duration_s=rest_detector.rest_duration_s,
            voltage_slope_v_per_s=rest_detector.voltage_slope_v_per_s,
        )
        if correction is not None and correction.applied:
            counter.soc = correction.soc
            status = "REST_OCV_CORRECTED"

        row = _base_row(current, counter.soc, status)
        row["predicted_soc"] = update.raw_soc
        row["correction"] = 0.0 if correction is None else correction.correction
        row["rest_eligible"] = bool(eligible)
        row["ocv_status"] = ocv_status
        rows.append(row)
        previous = current
    return rows


def replay_observer(
    observer: ECMObserver,
    samples: Sequence[MeasurementSample],
    maximum_gap_s: float = 2.0,
) -> list[dict[str, Any]]:
    """ECM 端电压残差反馈观测器回放（生产版，含无效电压纯预测路径）。"""
    sequence = list(samples)
    if len(sequence) < 2:
        raise ValueError("Insufficient samples")
    rows: list[dict[str, Any]] = [
        {
            "time_s": float(sequence[0].time_s),
            "estimated_soc": observer.counter.soc,
            "predicted_soc": observer.counter.soc,
            "predicted_voltage_v": None,
            "voltage_residual_v": None,
            "correction": 0.0,
            "status": "INITIAL",
            "trusted": True,
        }
    ]
    previous = sequence[0]
    after_gap = False
    for current in sequence[1:]:
        dt = float(current.time_s) - float(previous.time_s)
        reason = _gap_status(previous, current, maximum_gap_s)
        if reason == "INVALID_CURRENT":
            rows.append(_base_row(current, None, reason))
            previous = current
            continue
        if reason == "DATA_GAP":
            rows.append(_base_row(current, None, reason))
            after_gap = True
            previous = current
            continue

        if current.voltage_valid:
            result = observer.step(
                previous_current_a=previous.current_a,
                current_a=current.current_a,
                measured_voltage_v=current.terminal_voltage_v,
                dt_s=dt,
            )
            residual = result.residual_v
            predicted_voltage = result.predicted_voltage_v
            correction = result.correction
            status = result.status
            soc_estimate = result.soc
        else:
            # 纯电流预测：仍推进 SOC 与 RC，但禁止电压修正。
            update = observer.counter.step(previous.current_a, dt)
            observer.update_rc(previous.current_a, dt)
            ocv = observer.ocv_model.voltage_at(update.soc)
            predicted_voltage = ocv - current.current_a * observer.r0_ohm - sum(observer.polarization)
            result = ObserverResult(
                soc=update.soc,
                predicted_soc=update.soc,
                predicted_voltage_v=float(predicted_voltage),
                residual_v=float("nan"),
                correction=0.0,
                status="PREDICT_ONLY_INVALID_VOLTAGE",
                unclipped_soc=update.soc,
                saturated=False,
            )
            residual = float("nan")
            correction = 0.0
            status = result.status
            soc_estimate = result.soc

        if after_gap:
            status = "RESUMED_AFTER_GAP"
            after_gap = False

        rows.append(
            {
                "time_s": float(current.time_s),
                "estimated_soc": soc_estimate,
                "predicted_soc": result.predicted_soc,
                "predicted_voltage_v": predicted_voltage,
                "voltage_residual_v": residual,
                "correction": correction,
                "status": status,
                "trusted": True,
                "saturated": bool(getattr(result, "saturated", False)),
            }
        )
        previous = current
    return rows


def summarize_replay(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """回放通用摘要：覆盖率、缺口与异常计数。"""
    if not rows:
        raise ValueError("Empty replay")
    total = len(rows)
    valid = sum(1 for row in rows if row.get("soc", row.get("estimated_soc")) is not None)
    statuses: dict[str, int] = {}
    for row in rows:
        key = str(row.get("status", "UNKNOWN"))
        statuses[key] = statuses.get(key, 0) + 1
    return {
        "sample_count": int(total),
        "valid_count": int(valid),
        "coverage_fraction": float(valid / total),
        "status_counts": statuses,
        "data_gap_count": int(statuses.get("DATA_GAP", 0)),
        "invalid_current_count": int(statuses.get("INVALID_CURRENT", 0)),
        "invalid_voltage_count": int(statuses.get("INVALID_VOLTAGE", 0)),
        "soc_bound_reached_count": int(statuses.get("SOC_BOUND_REACHED", 0)),
        "rest_corrected_count": int(statuses.get("REST_OCV_CORRECTED", 0)),
    }

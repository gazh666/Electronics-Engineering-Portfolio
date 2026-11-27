"""电源工程指标计算。

这些公式用于把原始测量数据转换为工程可读指标，适用于任何电源类 DUT。
所有函数都对非有限值（NaN / ±inf）做显式校验，避免无效数据静默进入报告。

本模块**不实现**输出纹波与瞬态响应：当前 DUT 行为模型没有时间序列和
开关波形，无法计算这类指标。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

#: 效率物理上限。超过该值只标记数据异常，绝不截断为 100%。
EFFICIENCY_LIMIT_PERCENT = 100.0

#: 测试记录的有效状态
VALID_STATUSES = frozenset({"PASS", "FAIL", "ERROR", "SKIP"})


# ---------------------------------------------------------------------------
# 内部校验
# ---------------------------------------------------------------------------


def _require_finite(value: float, label: str) -> float:
    """把输入转换为有限浮点数，否则抛出 ValueError。"""
    if isinstance(value, bool):
        raise ValueError(f"{label} 不能是布尔值，收到 {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} 必须是数字，收到 {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须是有限数值，收到 {value!r}")
    return number


def _require_non_negative(value: float, label: str) -> float:
    number = _require_finite(value, label)
    if number < 0:
        raise ValueError(f"{label} 不能为负，收到 {number:g}")
    return number


# ---------------------------------------------------------------------------
# 功率与效率
# ---------------------------------------------------------------------------


def input_power(vin: float, iin: float) -> float:
    """输入功率 Pin = Vin × Iin（W）。"""
    return _require_non_negative(vin, "输入电压") * _require_non_negative(
        iin, "输入电流"
    )


def output_power(vout: float, iout: float) -> float:
    """输出功率 Pout = Vout × Iout（W）。"""
    return _require_non_negative(vout, "输出电压") * _require_non_negative(
        iout, "输出电流"
    )


def efficiency_percent(
    vin: float, iin: float, vout: float, iout: float
) -> float | None:
    """效率（%）= Pout / Pin × 100。

    输入功率为 0（例如空载、输出关断）时效率无定义，返回 ``None``。
    结果可能大于 100%，调用方应使用 :func:`efficiency_anomaly` 标记异常，
    **不得**截断为 100%。
    """
    pin = input_power(vin, iin)
    pout = output_power(vout, iout)
    if pin <= 0:
        return None
    return pout / pin * 100.0


def efficiency_anomaly(efficiency_percent: float | None) -> str | None:
    """检查效率是否超出物理上限。

    Returns
    -------
    str | None
        超过 100% 时返回异常描述，否则返回 ``None``。原始数值保持不变，
        由调用方决定记录为数据异常（例如测试状态 ERROR）。
    """
    if efficiency_percent is None:
        return None
    value = _require_finite(efficiency_percent, "效率")
    if value > EFFICIENCY_LIMIT_PERCENT:
        return (
            f"效率 {value:.3f}% 超过物理上限 {EFFICIENCY_LIMIT_PERCENT:.0f}%，"
            "数据异常（未截断）"
        )
    return None


# ---------------------------------------------------------------------------
# 电压误差
# ---------------------------------------------------------------------------


def voltage_absolute_error(measured: float, reference: float) -> float:
    """输出电压绝对误差（V）= |Vmeasured - Vreference|。"""
    measured_value = _require_finite(measured, "测量电压")
    reference_value = _require_finite(reference, "参考电压")
    return abs(measured_value - reference_value)


def voltage_error_percent(measured: float, reference: float) -> float:
    """输出电压相对误差（%）= |Vmeasured - Vreference| / Vreference × 100。

    参考电压必须为正数，否则相对误差无意义。
    """
    measured_value = _require_finite(measured, "测量电压")
    reference_value = _require_finite(reference, "参考电压")
    if reference_value <= 0:
        raise ValueError("参考电压必须大于零")
    return abs(measured_value - reference_value) / reference_value * 100.0


# ---------------------------------------------------------------------------
# 调整率
# ---------------------------------------------------------------------------


def load_regulation_percent(
    no_load_voltage: float, full_load_voltage: float, nominal_voltage: float
) -> float:
    """负载调整率（%）= |V空载 - V满载| / V标称 × 100。

    定义说明
    --------
    本平台统一以**标称输出电压**作为分母，便于不同用例之间横向比较。
    部分产品规范采用**空载输出电压**作分母：``(V空载 - V满载) / V空载``，
    相同数据会得到略有差异的结果（例如空载 5.1 V、满载 5.0 V、标称 5.0 V
    时，本定义为 2%，空载分母定义为 1.96%）。对比外部规范时必须确认分母。
    """
    no_load = _require_non_negative(no_load_voltage, "空载电压")
    full_load = _require_non_negative(full_load_voltage, "满载电压")
    nominal = _require_finite(nominal_voltage, "标称电压")
    if nominal <= 0:
        raise ValueError("标称电压必须大于零")
    return abs(no_load - full_load) / nominal * 100.0


def line_regulation_percent(
    v_low_line: float, v_high_line: float, vin_low: float, vin_high: float
) -> float:
    """线性调整率（%）：输入电压变化引起的输出变化比例。"""
    if vin_high == vin_low:
        raise ValueError("输入电压区间不能为零")
    low = _require_non_negative(v_low_line, "低压输入时输出电压")
    high = _require_non_negative(v_high_line, "高压输入时输出电压")
    if low <= 0:
        raise ValueError("输出电压必须大于零")
    return abs(high - low) / low * 100.0


# ---------------------------------------------------------------------------
# 第六阶段：统一工程指标接口
# ---------------------------------------------------------------------------


def power_watts(voltage: float, current: float) -> float:
    """功率（W）= 电压 × 电流，电压/电流必须为非负有限数。"""
    return _require_non_negative(voltage, "电压") * _require_non_negative(
        current, "电流"
    )


def voltage_error_volts(measured: float, reference: float) -> float:
    """带符号的电压绝对误差（V）= Vmeasured - Vreference。

    正值表示输出偏高，负值表示输出偏低；与旧接口
    :func:`voltage_absolute_error` 的绝对值语义不同。
    """
    measured_value = _require_finite(measured, "测量电压")
    reference_value = _require_finite(reference, "参考电压")
    return measured_value - reference_value


def signed_voltage_error_percent(measured: float, reference: float) -> float:
    """带符号的电压相对误差（%）= (Vmeasured - Vreference) / Vreference × 100。"""
    reference_value = _require_finite(reference, "参考电压")
    if reference_value <= 0:
        raise ValueError("参考电压必须大于零")
    return voltage_error_volts(measured, reference_value) / reference_value * 100.0


def absolute_voltage_error_percent(measured: float, reference: float) -> float:
    """绝对百分比电压误差（%），用于限值判定，不带方向。"""
    return abs(signed_voltage_error_percent(measured, reference))


def power_loss_watts(vin: float, iin: float, vout: float, iout: float) -> float:
    """功率损耗（W）= Pin - Pout。

    允许结果为负，以便数据质量模块发现“输出功率大于输入功率”的异常；
    本函数不静默截断。
    """
    return input_power(vin, iin) - output_power(vout, iout)


def line_regulation_span_percent(
    output_voltages: Sequence[float], nominal_voltage: float
) -> float:
    """线性调整率（%）= (Vout_max - Vout_min) / Vnominal × 100。

    要求输入电压变化、负载固定且所有采样均处于正常稳压状态。
    """
    values = [
        _require_non_negative(value, "输出电压") for value in output_voltages
    ]
    if len(values) < 2:
        raise ValueError("线性调整率至少需要两个采样点")
    nominal = _require_finite(nominal_voltage, "标称电压")
    if nominal <= 0:
        raise ValueError("标称电压必须大于零")
    return (max(values) - min(values)) / nominal * 100.0


def line_regulation_mv_per_v(
    vin_min: float, vin_max: float, vout_min: float, vout_max: float
) -> float:
    """线性调整率（mV/V）= |ΔVout| × 1000 / |ΔVin|。"""
    values = [
        _require_finite(value, "电压")
        for value in (vin_min, vin_max, vout_min, vout_max)
    ]
    vin_min, vin_max, vout_min, vout_max = values
    delta_vin = abs(vin_max - vin_min)
    if delta_vin == 0:
        raise ValueError("输入电压变化量不能为零")
    return abs(vout_max - vout_min) * 1000.0 / delta_vin


@dataclass(frozen=True)
class PerformanceMetrics:
    """单条正常工况记录的工程指标集合。"""

    input_power_w: float
    output_power_w: float
    power_loss_w: float
    efficiency_percent: float | None
    voltage_error_v: float
    voltage_error_percent: float
    absolute_voltage_error_percent: float


def calculate_metrics(
    vin: float,
    iin: float,
    vout: float,
    iout: float,
    nominal_voltage: float,
) -> PerformanceMetrics:
    """统一计算一组工程指标；保留带符号误差与绝对值误差。"""
    return PerformanceMetrics(
        input_power_w=input_power(vin, iin),
        output_power_w=output_power(vout, iout),
        power_loss_w=power_loss_watts(vin, iin, vout, iout),
        efficiency_percent=efficiency_percent(vin, iin, vout, iout),
        voltage_error_v=voltage_error_volts(vout, nominal_voltage),
        voltage_error_percent=signed_voltage_error_percent(vout, nominal_voltage),
        absolute_voltage_error_percent=absolute_voltage_error_percent(
            vout, nominal_voltage
        ),
    )


# ---------------------------------------------------------------------------
# 测试结果统计与数据完整性
# ---------------------------------------------------------------------------


def pass_rate_percent(statuses: Iterable[str]) -> float | None:
    """测试通过率（%）= PASS / (PASS + FAIL + ERROR) × 100。

    ``SKIP`` 用例未执行，不计入分母；没有任何有效用例时返回 ``None``。
    未知状态视为配置错误，直接抛出 ValueError，避免静默掩盖问题。
    """
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for status in statuses:
        if status not in VALID_STATUSES:
            raise ValueError(f"未知测试状态: {status!r}")
        counts[status] += 1

    executed = counts["PASS"] + counts["FAIL"] + counts["ERROR"]
    if executed == 0:
        return None
    return counts["PASS"] / executed * 100.0


def missing_fields(
    record: dict[str, Any],
    required_fields: Sequence[str],
    *,
    allow_none: Iterable[str] = (),
) -> list[str]:
    """检测记录中缺失的数据字段。

    以下情况都视为缺失：

    - 字段不存在；
    - 值为 ``None``（``allow_none`` 中的字段除外）；
    - 浮点值为 NaN / ±inf；
    - 字符串为空或仅含空白。
    """
    allowed = set(allow_none)
    missing: list[str] = []

    for name in required_fields:
        if name not in record:
            missing.append(name)
            continue

        value = record[name]
        if value is None:
            if name not in allowed:
                missing.append(name)
        elif isinstance(value, float) and not math.isfinite(value):
            missing.append(name)
        elif isinstance(value, str) and not value.strip():
            missing.append(name)

    return missing


# ---------------------------------------------------------------------------
# 统计辅助
# ---------------------------------------------------------------------------


def mean(values: list[float]) -> float:
    """算术平均值。"""
    if not values:
        raise ValueError("样本为空")
    return statistics.fmean(values)


def std(values: list[float]) -> float:
    """样本标准差（n-1）。"""
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def summarize(values: list[float]) -> dict[str, float]:
    """返回均值/标准差/最小/最大值，供报告展示。"""
    if not values:
        raise ValueError("样本为空")
    return {
        "mean": mean(values),
        "std": std(values),
        "min": min(values),
        "max": max(values),
    }

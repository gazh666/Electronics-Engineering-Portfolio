"""工程限值检查与验收汇总（Task 34/39）。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class ValidationError(ValueError):
    """限值检查输入非法。"""


def check(
    name: str,
    value: Any,
    threshold: Any,
    comparator: str,
    *,
    source: str = "",
    note: str = "",
    tolerance: float = 0.0,
) -> dict[str, Any]:
    if comparator not in ("<=", ">=", "<", ">", "==", "!="):
        raise ValidationError(f"未知比较符: {comparator}")
    if isinstance(value, (int, float)) and isinstance(threshold, (int, float)):
        passed = {
            "<=": value <= threshold + tolerance,
            ">=": value >= threshold - tolerance,
            "<": value < threshold,
            ">": value > threshold,
            "==": value == threshold,
            "!=": value != threshold,
        }[comparator]
    else:
        passed = value == threshold if comparator == "==" else value != threshold
    return {
        "check": name,
        "value": value,
        "threshold": threshold,
        "comparator": comparator,
        "status": "PASS" if passed else "FAIL",
        "source": source,
        "note": note,
    }


def summarize_checks(checks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in checks if item.get("status") == "PASS")
    failed = sum(1 for item in checks if item.get("status") == "FAIL")
    return {
        "checks": list(checks),
        "passed": passed,
        "failed": failed,
        "overall": "PASS" if failed == 0 else "FAIL",
    }


def voltage_checks(
    *,
    ideal_error_v: float,
    calibrated_max_error_v: float,
    calibrated_rmse_v: float,
    saturation_ratio: float,
    limits: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ideal = limits["ideal_consistency"]
    non_ideal = limits["non_ideal_measurement"]
    return [
        check(
            "理想差分放大理论与 SPICE 误差 (mV)",
            ideal_error_v * 1000.0,
            float(ideal["divider_and_diff_amp_theory_vs_spice_v"]) * 1000.0,
            "<=",
            source="circuits/differential_amplifier.py",
        ),
        check(
            "单体电压最大采集误差（校准后）(mV)",
            calibrated_max_error_v * 1000.0,
            float(non_ideal["cell_voltage_max_error_v"]) * 1000.0,
            "<=",
            source="analysis/tolerance_analysis.py",
        ),
        check(
            "单体电压 RMSE（校准后）(mV)",
            calibrated_rmse_v * 1000.0,
            float(non_ideal["cell_voltage_max_error_v"]) * 1000.0,
            "<=",
            source="analysis/tolerance_analysis.py",
        ),
        check(
            "正常工作范围 ADC 饱和比例",
            saturation_ratio,
            0.0,
            "==",
            source="sensing/measurement_chain.py",
        ),
    ]


def current_checks(
    *,
    ideal_error_v: float,
    calibrated_max_error_a: float,
    calibrated_rmse_a: float,
    limits: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ideal = limits["ideal_consistency"]
    non_ideal = limits["non_ideal_measurement"]
    return [
        check(
            "理想双向电流理论与 SPICE 误差 (mV)",
            ideal_error_v * 1000.0,
            float(ideal["bidirectional_current_theory_vs_spice_v"]) * 1000.0,
            "<=",
            source="circuits/current_sensing.py",
        ),
        check(
            "双向电流最大采集误差（校准后）(mA)",
            calibrated_max_error_a * 1000.0,
            float(non_ideal["current_max_error_a"]) * 1000.0,
            "<=",
            source="analysis/tolerance_analysis.py",
        ),
        check(
            "双向电流 RMSE（校准后）(mA)",
            calibrated_rmse_a * 1000.0,
            float(non_ideal["current_max_error_a"]) * 1000.0,
            "<=",
            source="analysis/tolerance_analysis.py",
        ),
    ]


def filter_checks(
    *,
    cutoff_relative_error: float,
    attenuation_100khz_db: float,
    rise_time_relative_error: float,
    limits: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ideal = limits["ideal_consistency"]
    return [
        check(
            "RC 截止频率相对误差",
            cutoff_relative_error,
            float(ideal["rc_cutoff_frequency_relative_error"]),
            "<=",
            source="circuits/rc_filter.py",
        ),
        check(
            "100 kHz 差模干扰衰减 (dB)",
            attenuation_100khz_db,
            -20.0,
            "<=",
            source="circuits/rc_filter.py",
            note="教学设计参考：至少 20 dB 衰减",
        ),
        check(
            "RC 阶跃上升时间相对误差",
            abs(rise_time_relative_error),
            0.05,
            "<=",
            source="circuits/rc_filter.py",
        ),
    ]


def adc_checks(
    *,
    max_quantization_error_lsb: float,
    monotonic: bool,
    limits: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ideal = limits["ideal_consistency"]
    return [
        check(
            "ADC 最大量化误差 (LSB)",
            max_quantization_error_lsb,
            float(ideal["adc_quantization_error_lsb"]),
            "<=",
            source="sensing/adc.py",
            note="限值 0.5 LSB 不变；1e-9 仅用于吸收二进制浮点表示误差",
            tolerance=1e-9,
        ),
        check("ADC 码值单调性", bool(monotonic), True, "==", source="sensing/adc.py"),
    ]


def temperature_checks(
    *,
    calibrated_max_error_c: float,
    calibrated_rmse_c: float,
    limits: Mapping[str, Any],
) -> list[dict[str, Any]]:
    non_ideal = limits["non_ideal_measurement"]
    return [
        check(
            "NTC 最大温度误差（校准后）(℃)",
            calibrated_max_error_c,
            float(non_ideal["ntc_max_temperature_error_c"]),
            "<=",
            source="analysis/tolerance_analysis.py",
        ),
        check(
            "NTC 温度 RMSE（校准后）(℃)",
            calibrated_rmse_c,
            float(non_ideal["ntc_max_temperature_error_c"]),
            "<=",
            source="analysis/tolerance_analysis.py",
        ),
    ]

"""Buck 理论与 SPICE 对照验证。

验证项明确区分：

- ``numerical_accuracy``：频率 / 占空比等数值一致性；
- ``model_difference``：理想理论与非理想模型的差异；
- ``mode_applicability``：CCM 理论是否适用于当前工作模式；
- ``energy_balance``：电感伏秒平衡与电容电荷平衡；
- ``design_target``：输出纹波设计目标；
- ``data_quality``：波形是否可用。

当 CCM 理论不适用于 DCM 时标记 ``NOT_APPLICABLE``，未达到稳态时标记
``NOT_SETTLED``，不伪造 PASS。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from analysis.conduction_mode import ConductionMode
from analysis.steady_state import STATUS_STEADY_STATE
from circuits.validators import finite_number, positive_number

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VALIDATION_CONFIG_PATH = PROJECT_ROOT / "configs" / "buck_validation.yaml"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_NOT_SETTLED = "NOT_SETTLED"
STATUS_ERROR = "ERROR"


@dataclass(frozen=True)
class BuckValidationLimits:
    """验证限值（项目教学假设，不是商业规格）。"""

    frequency_relative_error_max: float = 0.01
    duty_absolute_error_max: float = 0.005
    ideal_ccm_voltage_relative_error_max: float = 0.10
    inductor_ripple_relative_error_max: float = 0.15
    capacitor_ripple_relative_error_max: float = 0.25
    output_ripple_design_limit_vpp: float = 0.05
    volt_second_relative_error_max: float = 0.15
    charge_balance_relative_error_max: float = 0.15

    def __post_init__(self) -> None:
        for name in (
            "frequency_relative_error_max",
            "ideal_ccm_voltage_relative_error_max",
            "inductor_ripple_relative_error_max",
            "capacitor_ripple_relative_error_max",
            "output_ripple_design_limit_vpp",
            "volt_second_relative_error_max",
            "charge_balance_relative_error_max",
        ):
            positive_number(getattr(self, name), f"checks.{name}")
        positive_number(self.duty_absolute_error_max, "checks.duty_absolute_error_max")

    def to_dict(self) -> dict[str, float]:
        return {
            "frequency_relative_error_max": self.frequency_relative_error_max,
            "duty_absolute_error_max": self.duty_absolute_error_max,
            "ideal_ccm_voltage_relative_error_max": self.ideal_ccm_voltage_relative_error_max,
            "inductor_ripple_relative_error_max": self.inductor_ripple_relative_error_max,
            "capacitor_ripple_relative_error_max": self.capacitor_ripple_relative_error_max,
            "output_ripple_design_limit_vpp": self.output_ripple_design_limit_vpp,
            "volt_second_relative_error_max": self.volt_second_relative_error_max,
            "charge_balance_relative_error_max": self.charge_balance_relative_error_max,
        }


@dataclass(frozen=True)
class ValidationCheck:
    """单个验证项。"""

    name: str
    category: str
    status: str
    measured: float | None
    reference: float | None
    error: float | None
    tolerance: float | None
    unit: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in (
            STATUS_PASS,
            STATUS_FAIL,
            STATUS_NOT_APPLICABLE,
            STATUS_NOT_SETTLED,
            STATUS_ERROR,
        ):
            raise ValueError(f"unknown validation status: {self.status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "measured": self.measured,
            "reference": self.reference,
            "error": self.error,
            "tolerance": self.tolerance,
            "unit": self.unit,
            "note": self.note,
        }


@dataclass(frozen=True)
class BuckValidationReport:
    """验证报告集合。"""

    checks: tuple[ValidationCheck, ...]
    limits: BuckValidationLimits

    @property
    def status(self) -> str:
        statuses = [check.status for check in self.checks]
        if STATUS_FAIL in statuses:
            return STATUS_FAIL
        if STATUS_ERROR in statuses:
            return STATUS_ERROR
        if STATUS_NOT_SETTLED in statuses:
            return STATUS_NOT_SETTLED
        return STATUS_PASS

    @property
    def summary(self) -> dict[str, int]:
        counts = {
            STATUS_PASS: 0,
            STATUS_FAIL: 0,
            STATUS_NOT_APPLICABLE: 0,
            STATUS_NOT_SETTLED: 0,
            STATUS_ERROR: 0,
        }
        for check in self.checks:
            counts[check.status] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "limits": self.limits.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
            "data_source": "comparison",
            "specification_type": "project_assumption",
        }


def load_buck_validation_config(
    path: str | Path = DEFAULT_VALIDATION_CONFIG_PATH,
) -> BuckValidationLimits:
    """读取 ``configs/buck_validation.yaml``。"""
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件根节点必须是映射: {config_path}")
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("验证配置缺少 checks 映射段")

    required = (
        "frequency_relative_error_max",
        "duty_absolute_error_max",
        "ideal_ccm_voltage_relative_error_max",
        "inductor_ripple_relative_error_max",
        "capacitor_ripple_relative_error_max",
        "output_ripple_design_limit_vpp",
        "volt_second_relative_error_max",
        "charge_balance_relative_error_max",
    )
    missing = [name for name in required if name not in checks]
    if missing:
        raise ValueError(f"验证配置缺少字段: {missing}")
    return BuckValidationLimits(**{name: checks[name] for name in required})


def _relative_error(measured: float, reference: float) -> float:
    reference = float(reference)
    if reference == 0:
        raise ValueError("relative error is undefined for a zero reference")
    return (float(measured) - reference) / reference


def _check_relative(
    name: str,
    category: str,
    measured: float | None,
    reference: float,
    limit: float,
    *,
    unit: str,
    applicable: bool = True,
    steady: bool = True,
    note: str = "",
) -> ValidationCheck:
    if not applicable:
        return ValidationCheck(
            name=name,
            category=category,
            status=STATUS_NOT_APPLICABLE,
            measured=measured,
            reference=reference,
            error=None,
            tolerance=limit,
            unit=unit,
            note=note or "theoretical relationship does not apply to the identified operating mode",
        )
    if measured is None:
        return ValidationCheck(
            name=name,
            category=category,
            status=STATUS_NOT_SETTLED,
            measured=None,
            reference=reference,
            error=None,
            tolerance=limit,
            unit=unit,
            note=note or "measured value is unavailable",
        )
    if not steady:
        return ValidationCheck(
            name=name,
            category=category,
            status=STATUS_NOT_SETTLED,
            measured=float(measured),
            reference=reference,
            error=None,
            tolerance=limit,
            unit=unit,
            note=note or "steady state has not been established",
        )
    error = _relative_error(measured, reference)
    return ValidationCheck(
        name=name,
        category=category,
        status=STATUS_PASS if abs(error) <= limit else STATUS_FAIL,
        measured=float(measured),
        reference=reference,
        error=float(error),
        tolerance=limit,
        unit=unit,
        note=note,
    )


def validate_buck_converter(
    *,
    expected_frequency_hz: float,
    measured_frequency_hz: float,
    expected_duty_cycle: float,
    measured_duty_cycle: float,
    ideal_ccm_voltage_v: float,
    measured_output_voltage_v: float | None,
    ccm_assumption_valid: bool,
    theoretical_inductor_ripple_app: float,
    measured_inductor_ripple_app: float | None,
    theoretical_capacitor_ripple_vpp: float,
    measured_output_ripple_vpp: float | None,
    simulated_mode: ConductionMode,
    theoretical_mode: ConductionMode,
    steady_state_status: str,
    volt_second: Mapping[str, Any] | None,
    charge_balance: Mapping[str, Any] | None,
    waveform_quality_ok: bool = True,
    limits: BuckValidationLimits | None = None,
) -> BuckValidationReport:
    """执行完整对照验证，返回逐项结果。"""
    limits = limits or BuckValidationLimits()
    if not isinstance(limits, BuckValidationLimits):
        raise ValueError("limits must be BuckValidationLimits")
    if not isinstance(simulated_mode, ConductionMode):
        raise ValueError("simulated_mode must be ConductionMode")
    if not isinstance(theoretical_mode, ConductionMode):
        raise ValueError("theoretical_mode must be ConductionMode")

    expected_frequency = positive_number(expected_frequency_hz, "expected_frequency_hz")
    measured_frequency = positive_number(measured_frequency_hz, "measured_frequency_hz")
    expected_duty = finite_number(expected_duty_cycle, "expected_duty_cycle")
    measured_duty = finite_number(measured_duty_cycle, "measured_duty_cycle")
    ideal_voltage = positive_number(ideal_ccm_voltage_v, "ideal_ccm_voltage_v")
    theoretical_ripple_i = positive_number(
        theoretical_inductor_ripple_app, "theoretical_inductor_ripple_app"
    )
    theoretical_ripple_v = positive_number(
        theoretical_capacitor_ripple_vpp, "theoretical_capacitor_ripple_vpp"
    )

    steady = steady_state_status == STATUS_STEADY_STATE
    ccm_applicable = bool(ccm_assumption_valid) and simulated_mode != ConductionMode.DCM

    checks: list[ValidationCheck] = []

    frequency_error = _relative_error(measured_frequency, expected_frequency)
    checks.append(
        ValidationCheck(
            name="pwm_frequency_matches_target",
            category="numerical_accuracy",
            status=(
                STATUS_PASS
                if abs(frequency_error) <= limits.frequency_relative_error_max
                else STATUS_FAIL
            ),
            measured=float(measured_frequency),
            reference=float(expected_frequency),
            error=float(frequency_error),
            tolerance=limits.frequency_relative_error_max,
            unit="relative",
            note="measured from real gate threshold crossings",
        )
    )

    duty_error = measured_duty - expected_duty
    checks.append(
        ValidationCheck(
            name="pwm_duty_matches_config",
            category="numerical_accuracy",
            status=(
                STATUS_PASS
                if abs(duty_error) <= limits.duty_absolute_error_max
                else STATUS_FAIL
            ),
            measured=float(measured_duty),
            reference=float(expected_duty),
            error=float(duty_error),
            tolerance=limits.duty_absolute_error_max,
            unit="absolute",
            note="threshold-crossing duty, not the configured value copied back",
        )
    )

    checks.append(
        _check_relative(
            "ideal_ccm_output_voltage",
            "model_difference",
            measured_output_voltage_v,
            ideal_voltage,
            limits.ideal_ccm_voltage_relative_error_max,
            unit="relative",
            applicable=ccm_applicable,
            steady=steady,
            note=(
                "ideal D*Vin does not include switch RON and diode forward drop"
                if ccm_applicable
                else "ideal CCM voltage is not applicable: waveform indicates DCM"
            ),
        )
    )
    checks.append(
        _check_relative(
            "inductor_current_ripple",
            "model_difference",
            measured_inductor_ripple_app,
            theoretical_ripple_i,
            limits.inductor_ripple_relative_error_max,
            unit="relative",
            applicable=ccm_applicable,
            steady=steady,
            note="CCM ripple formula (Vin - Vout) * D / (L * f)",
        )
    )
    checks.append(
        _check_relative(
            "output_voltage_ripple",
            "model_difference",
            measured_output_ripple_vpp,
            theoretical_ripple_v,
            limits.capacitor_ripple_relative_error_max,
            unit="relative",
            applicable=ccm_applicable,
            steady=steady,
            note="ideal capacitor ripple dIL / (8 f C) ignores ESR/ESL",
        )
    )

    if (
        simulated_mode in (ConductionMode.BOUNDARY_OR_UNCERTAIN, ConductionMode.INVALID)
        or theoretical_mode is ConductionMode.BOUNDARY_OR_UNCERTAIN
        or not steady
    ):
        checks.append(
            ValidationCheck(
                name="conduction_mode_matches_theory",
                category="mode_applicability",
                status=(
                    STATUS_NOT_SETTLED
                    if not steady
                    else STATUS_NOT_APPLICABLE
                ),
                measured=None,
                reference=None,
                error=None,
                tolerance=None,
                note=(
                    "steady state not established"
                    if not steady
                    else "mode is at the boundary or uncertain; no forced CCM/DCM claim"
                ),
            )
        )
    else:
        checks.append(
            ValidationCheck(
                name="conduction_mode_matches_theory",
                category="mode_applicability",
                status=(
                    STATUS_PASS if simulated_mode is theoretical_mode else STATUS_FAIL
                ),
                measured=None,
                reference=None,
                error=None,
                tolerance=None,
                note=f"simulated={simulated_mode.value}, theoretical={theoretical_mode.value}",
            )
        )

    if not steady:
        balance_status = STATUS_NOT_SETTLED
        balance_note = "steady state not established; balance integrals are not evaluated"
    else:
        balance_status = None
        balance_note = ""

    for name, payload, limit, unit, category in (
        (
            "inductor_volt_second_balance",
            volt_second,
            limits.volt_second_relative_error_max,
            "relative",
            "energy_balance",
        ),
        (
            "capacitor_charge_balance",
            charge_balance,
            limits.charge_balance_relative_error_max,
            "relative",
            "energy_balance",
        ),
    ):
        if not steady:
            checks.append(
                ValidationCheck(
                    name=name,
                    category=category,
                    status=STATUS_NOT_SETTLED,
                    measured=None,
                    reference=None,
                    error=None,
                    tolerance=limit,
                    unit=unit,
                    note=balance_note,
                )
            )
            continue
        relative = None if payload is None else payload.get("relative_error")
        if relative is None:
            status = STATUS_NOT_APPLICABLE
            note = "balance error could not be normalized"
        else:
            relative = float(relative)
            status = STATUS_PASS if relative <= limit else STATUS_FAIL
            note = "integral of instantaneous quantity versus L*dI or C*dV"
        checks.append(
            ValidationCheck(
                name=name,
                category=category,
                status=status,
                measured=relative,
                reference=0.0,
                error=relative,
                tolerance=limit,
                unit=unit,
                note=note,
            )
        )

    if steady and measured_output_ripple_vpp is not None:
        measured_ripple = float(measured_output_ripple_vpp)
        checks.append(
            ValidationCheck(
                name="output_ripple_design_limit",
                category="design_target",
                status=(
                    STATUS_PASS
                    if measured_ripple <= limits.output_ripple_design_limit_vpp
                    else STATUS_FAIL
                ),
                measured=measured_ripple,
                reference=limits.output_ripple_design_limit_vpp,
                error=measured_ripple - limits.output_ripple_design_limit_vpp,
                tolerance=limits.output_ripple_design_limit_vpp,
                unit="Vpp",
                note="project design target, not a commercial datasheet specification",
            )
        )
    else:
        checks.append(
            ValidationCheck(
                name="output_ripple_design_limit",
                category="design_target",
                status=STATUS_NOT_SETTLED,
                measured=measured_output_ripple_vpp,
                reference=limits.output_ripple_design_limit_vpp,
                error=None,
                tolerance=limits.output_ripple_design_limit_vpp,
                unit="Vpp",
                note="steady state not established",
            )
        )

    checks.append(
        ValidationCheck(
            name="waveform_data_quality",
            category="data_quality",
            status=STATUS_PASS if waveform_quality_ok else STATUS_FAIL,
            measured=None,
            reference=None,
            error=None,
            tolerance=None,
            note="time axis, finiteness and length consistency checks",
        )
    )

    return BuckValidationReport(checks=tuple(checks), limits=limits)

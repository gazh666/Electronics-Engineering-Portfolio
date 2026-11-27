"""任务 1：Buck 理论计算演示（不运行 SPICE）。

理论结果单独保存到 ``results/buck_stage3/theory_<run_id>.json``，
不会与任何 SPICE 波形混在一起。
"""

from __future__ import annotations

import sys
from typing import Any

from analysis.buck_theory import (
    calculate_ideal_buck,
    calculate_ideal_dcm,
    capacitance_for_ripple,
    inductor_for_ripple,
)
from circuits.buck_config import load_buck_config
from scripts.buck_common import STAGE3_RESULTS_ROOT
from storage.result_store import new_run_id, write_json


def analyze() -> dict[str, Any]:
    parameters = load_buck_config()
    theory = calculate_ideal_buck(parameters.circuit)
    dcm = calculate_ideal_dcm(parameters.circuit)

    checks: list[dict[str, Any]] = []

    def check(name: str, expected: float, actual: float, tolerance: float, unit: str) -> None:
        error = abs(actual - expected)
        checks.append(
            {
                "name": name,
                "expected": expected,
                "actual": actual,
                "absolute_error": error,
                "tolerance": tolerance,
                "unit": unit,
                "status": "PASS" if error <= tolerance else "FAIL",
            }
        )

    check("理想输出电压 D*Vin", 5.0, theory.ideal_output_voltage_v, 1e-9, "V")
    check("导通时间 D*T", 4.1666667e-6, theory.on_time_s, 1e-12, "s")
    check("截止时间 (1-D)*T", 5.8333333e-6, theory.off_time_s, 1e-12, "s")
    check("电感电流纹波", 0.6205674, theory.inductor_ripple_app, 1e-6, "A")
    check("临界电流 dIL/2", 0.3102837, theory.boundary_current_a, 1e-7, "A")
    check("临界负载电阻", 16.1144, theory.boundary_resistance_ohm, 1e-3, "Ω")
    check("输出纹波", 0.0077571, theory.capacitor_ripple_vpp, 1e-7, "Vpp")

    required_inductance = inductor_for_ripple(
        parameters.circuit.input_voltage_v,
        theory.ideal_output_voltage_v,
        parameters.circuit.duty_cycle,
        parameters.circuit.switching_frequency_hz,
        theory.inductor_ripple_app,
    )
    check("按纹波反推电感", parameters.circuit.inductance_h, required_inductance, 1e-9, "H")

    required_capacitance = capacitance_for_ripple(
        theory.inductor_ripple_app,
        parameters.circuit.switching_frequency_hz,
        theory.capacitor_ripple_vpp,
    )
    check("按纹波反推电容", parameters.circuit.capacitance_f, required_capacitance, 1e-9, "F")

    if dcm.dcm_assumption_valid:
        checks.append(
            {
                "name": "默认负载应处于 CCM（DCM 公式不适用）",
                "expected": False,
                "actual": dcm.dcm_assumption_valid,
                "status": "FAIL",
            }
        )
    else:
        checks.append(
            {
                "name": "默认负载应处于 CCM（DCM 公式不适用）",
                "expected": False,
                "actual": dcm.dcm_assumption_valid,
                "status": "PASS",
            }
        )

    payload: dict[str, Any] = {
        "run_id": new_run_id(),
        "analysis": "buck_ideal_theory",
        "data_source": "analytical_theory",
        "specification_type": "project_assumption",
        "parameters": parameters.to_dict(),
        "ideal_ccm": theory.to_dict(),
        "ideal_dcm": dcm.to_dict(),
        "design_inverse": {
            "inductor_for_measured_ripple_h": required_inductance,
            "capacitance_for_measured_ripple_f": required_capacitance,
        },
        "checks": checks,
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "notes": [
            "Ideal CCM formulas exclude switch RON, diode forward drop, ESR/ESL and control dynamics.",
            "The DCM formula is reported only to document its applicability limit at the default load.",
        ],
    }

    STAGE3_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    output = STAGE3_RESULTS_ROOT / f"theory_{payload['run_id']}.json"
    write_json(output, payload)
    payload["output_file"] = str(output)
    return payload


def main() -> int:
    result = analyze()
    print(f"Buck theory: {result['status']}")
    print(f"  Vout_ideal = {result['ideal_ccm']['ideal_output_voltage_v']:.6f} V")
    print(f"  dIL        = {result['ideal_ccm']['inductor_ripple_app']:.6f} A")
    print(f"  dVout      = {result['ideal_ccm']['capacitor_ripple_vpp']:.9f} V")
    print(f"  saved      = {result['output_file']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

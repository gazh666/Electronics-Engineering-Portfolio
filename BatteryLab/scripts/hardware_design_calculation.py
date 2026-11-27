"""第八阶段真实器件设计计算（全部为解析计算，不是硬件实测）。

运行：
    python -m scripts.hardware_design_calculation
    python -m scripts.hardware_design_calculation --output results/eda/run_xxx

输入参数全部来自官方数据手册，每个数值在 JSON 中带上 source 字段。
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime
from pathlib import Path

from eda_tools import (
    copper_calculations,
    design_calculations,
    feedback_design,
    inductor_design,
    thermal_calculations,
)

# ---------------------------------------------------------------- 数据手册常量
BQ76922_SENSE_FULL_SCALE_V = 0.2          # SLUSE86A p.11 coulomb counter ±200 mV
BQ76922_ADC_LSB_V = 1.24 / (5 * 2 ** 15)  # 7.568 µV，1 LSB = VREF2/(5*2^15)
BQ76922_INTERNAL_BALANCE_OHM = {"min": 15.0, "typ": 28.0, "max": 46.0}  # SLUSE86A 6.19 p.14
BQ76922_RTH_JA_C_PER_W = 33.2             # SLUSE86A 6.4 p.8
BQ76922_CELL_INPUT_R_OHM = 47.0           # 本设计选定，落在 20–100 Ω 推荐区间
BQ76922_CELL_INPUT_C_F = 0.22e-6          # 本设计选定，落在 0.1–1 µF 推荐区间

BQ24610_VFB_REF_V = 2.1                   # SLUS892D p.17 Equation 1
BQ24610_VREF_V = 3.3                      # SLUS892D p.4 VREF
BQ24610_K_TTC_MIN_PER_NF = 5.6            # SLUS892D p.18

CHARGE_TARGET_V = 12.15
CHARGE_CURRENT_A = 1.0
PRECHARGE_CURRENT_A = 0.1
INPUT_CURRENT_LIMIT_A = 1.5
SENSE_R_OHM = 0.01

# 器件实测/规格值（25℃ 典型值；最大 RDS(on) 用于降额）
CSD18540_RDS_MAX = 0.0022                 # SLPS488B p.3 VGS=10V max
CSD17578_RDS_MAX = 0.0069                 # SLPS526 p.3
CSD17581_RDS_MAX = 0.0034                 # SLPS630 p.3
SON_RTH_JA = 50.0                         # 1 in² 2 oz Cu，数据手册条件

SRN6045_220M_DCR = 0.142
SRN6045_220M_ISAT = 1.9
SRN6045_220M_IRMS = 1.5
INDUCTANCE_H = 22e-6
OUTPUT_C_NOMINAL_F = 9.4e-6


def _timestamp_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


def compute_design() -> dict:
    result: dict = {
        "disclaimer": "Engineering Prototype Design — Not Hardware Validated",
        "calculation_only": True,
        "sources": {
            "afe": "TI BQ76922 SLUSE86A (rev 2024-04)",
            "charger": "TI BQ24610 SLUS892D (rev 2019-12)",
            "mosfets": "TI CSD18540Q5B SLPS488B / CSD17578Q5A SLPS526 / CSD17581Q5A SLPS630",
            "shunt": "Vishay Dale WSL Document 30100 (rev 2026-11-20)",
            "inductor": "Bourns SRN6045 (rev 01/20)",
        },
    }

    # 1. 分流电阻候选
    candidates = []
    for resistance in (0.001, 0.002, 0.005, 0.010):
        rated = 1.0 if resistance <= 0.002 else 0.5
        shunt = design_calculations.calculate_shunt(2.5, resistance, rated)
        scale = design_calculations.calculate_shunt_scale(
            resistance, BQ76922_SENSE_FULL_SCALE_V, BQ76922_ADC_LSB_V
        )
        candidates.append(
            {
                "resistance_ohm": resistance,
                "rated_power_w": rated,
                **shunt,
                **scale,
                "current_resolution_ma": scale["current_lsb_a"] * 1000.0,
            }
        )
    result["shunt_candidates"] = candidates
    result["shunt_selected"] = {
        "resistance_ohm": SENSE_R_OHM,
        "part": "WSL2010R0100FEA",
        "tcr_ppm_per_c": 75,
        "bq76922_tc_recommendation_ppm_per_c": 50,
        "meets_tc_recommendation": False,
        "note": "BQ76922 p.62 要求分流电阻 TC ≤ 50 ppm/°C；WSL2010 为 ±75 ppm/°C，属于已知偏离",
    }

    # 2. 单体输入 RC
    result["cell_filter"] = {
        **design_calculations.calculate_differential_rc(
            BQ76922_CELL_INPUT_R_OHM,
            BQ76922_CELL_INPUT_R_OHM,
            BQ76922_CELL_INPUT_C_F,
            100e3,
        ),
        "series_resistance_ohm": BQ76922_CELL_INPUT_R_OHM,
        "capacitance_f": BQ76922_CELL_INPUT_C_F,
        "source": "SLUSE86A p.7 推荐 20–100 Ω / 0.1–0.22–1 µF",
    }

    # 3. 功率路径导通损耗
    bms_path = design_calculations.calculate_mosfet_path(
        2.5, [CSD18540_RDS_MAX, CSD18540_RDS_MAX]
    )
    bms_thermal_each = thermal_calculations.estimate_junction_temperature(
        25.0, bms_path["individual_losses_w"][0], SON_RTH_JA
    )
    result["bms_protection_path"] = {
        "mosfet": "CSD18540Q5B x2 (back-to-back)",
        "current_a": 2.5,
        **bms_path,
        "junction_temperature_each_c": bms_thermal_each["estimated_junction_temperature_c"],
        "thermal_basis": "RθJA 50 °C/W on 1 in² 2 oz Cu，数据手册条件，非本板实测",
    }

    # 4. 均衡支路（BQ76922 内部均衡 + 外部 47 Ω 滤波电阻）
    balancing = []
    for label, r_internal in BQ76922_INTERNAL_BALANCE_OHM.items():
        branch = design_calculations.calculate_balancing_branch(
            4.05, BQ76922_CELL_INPUT_R_OHM, r_internal
        )
        internal_power = branch["balancing_current_a"] ** 2 * r_internal
        junction = thermal_calculations.estimate_junction_temperature(
            25.0, internal_power, BQ76922_RTH_JA_C_PER_W
        )
        balancing.append(
            {
                "case": label,
                "internal_resistance_ohm": r_internal,
                **branch,
                "chip_internal_dissipation_w": internal_power,
                "chip_junction_temperature_c": junction["estimated_junction_temperature_c"],
            }
        )
    result["balancing"] = {
        "cases": balancing,
        "external_resistor_part": "47 Ω 需选 1206 0.25 W 或更大",
        "worst_case_external_power_w": max(c["resistor_power_w"] for c in balancing),
        "finding": "47 Ω 滤波电阻串在均衡路径内；内部均衡电阻最小时外部电阻功耗最高",
    }

    # 5. BQ24610 电压反馈
    divider = feedback_design.calculate_feedback_divider(
        CHARGE_TARGET_V, BQ24610_VFB_REF_V, 100_000.0
    )
    r2_choice = feedback_design.nearest_e96(divider["upper_resistance_ohm"])
    actual_v = feedback_design.calculate_actual_feedback_voltage(
        BQ24610_VFB_REF_V, r2_choice, 100_000.0
    )
    error_budget = feedback_design.calculate_divider_error_budget(
        BQ24610_VFB_REF_V,
        0.5,       # SLUS892D p.1 充电电压精度 ±0.5%
        r2_choice,
        100_000.0,
        0.5,       # 0.5% 电阻
        1e-7,      # VFB 偏置电流量级假设，需数据手册确认（标记 NOT_VERIFIED）
    )
    result["charger_voltage_feedback"] = {
        "reference_voltage_v": BQ24610_VFB_REF_V,
        "target_voltage_v": CHARGE_TARGET_V,
        "ideal_upper_ohm": divider["upper_resistance_ohm"],
        "selected_upper_ohm": r2_choice,
        "lower_ohm": 100_000.0,
        "actual_voltage_v": actual_v,
        "voltage_error_v": actual_v - CHARGE_TARGET_V,
        "voltage_error_percent": (actual_v - CHARGE_TARGET_V) / CHARGE_TARGET_V * 100.0,
        "error_budget": error_budget,
        "bias_current_status": "NOT_VERIFIED：VFB 偏置电流需在 Electrical Characteristics 中确认",
        "source": "SLUS892D p.17 Equation 1；p.1 ±0.5% 电压精度",
    }

    # 6. BQ24610 电流设定
    iset1_target_v = CHARGE_CURRENT_A * 20.0 * SENSE_R_OHM
    iset1_div = feedback_design.calculate_iset_divider(
        BQ24610_VREF_V, iset1_target_v, 10_000.0
    )
    iset1_top = feedback_design.nearest_e96(iset1_div["upper_resistance_ohm"])
    iset1_actual_v = BQ24610_VREF_V * 10_000.0 / (iset1_top + 10_000.0)
    iset1_current = feedback_design.calculate_bq24610_charge_current(
        iset1_actual_v, SENSE_R_OHM
    )

    iset2_target_v = PRECHARGE_CURRENT_A * 100.0 * SENSE_R_OHM
    iset2_div = feedback_design.calculate_iset_divider(
        BQ24610_VREF_V, iset2_target_v, 10_000.0
    )
    iset2_top = feedback_design.nearest_e96(iset2_div["upper_resistance_ohm"])
    iset2_actual_v = BQ24610_VREF_V * 10_000.0 / (iset2_top + 10_000.0)
    iset2_current = feedback_design.calculate_bq24610_precharge_current(
        iset2_actual_v, SENSE_R_OHM
    )

    acset_target_v = INPUT_CURRENT_LIMIT_A * 20.0 * SENSE_R_OHM
    acset_div = feedback_design.calculate_iset_divider(
        BQ24610_VREF_V, acset_target_v, 10_000.0
    )
    acset_top = feedback_design.nearest_e96(acset_div["upper_resistance_ohm"])
    acset_actual_v = BQ24610_VREF_V * 10_000.0 / (acset_top + 10_000.0)
    acset_current = feedback_design.calculate_bq24610_adapter_current(
        acset_actual_v, SENSE_R_OHM
    )

    result["charger_current_settings"] = {
        "sense_resistance_ohm": SENSE_R_OHM,
        "iset1": {
            "target_current_a": CHARGE_CURRENT_A,
            "target_voltage_v": iset1_target_v,
            "ideal_top_ohm": iset1_div["upper_resistance_ohm"],
            "selected_top_ohm": iset1_top,
            "actual_voltage_v": iset1_actual_v,
            "actual_current_a": iset1_current,
        },
        "iset2": {
            "target_current_a": PRECHARGE_CURRENT_A,
            "target_voltage_v": iset2_target_v,
            "ideal_top_ohm": iset2_div["upper_resistance_ohm"],
            "selected_top_ohm": iset2_top,
            "actual_voltage_v": iset2_actual_v,
            "actual_current_a": iset2_current,
        },
        "acset": {
            "target_current_a": INPUT_CURRENT_LIMIT_A,
            "target_voltage_v": acset_target_v,
            "ideal_top_ohm": acset_div["upper_resistance_ohm"],
            "selected_top_ohm": acset_top,
            "actual_voltage_v": acset_actual_v,
            "actual_current_a": acset_current,
        },
        "equations": {
            "icharge": "V_ISET1 / (20 × R_SR)",
            "iprecharge": "V_ISET2 / (100 × R_SR)",
            "iac": "V_ACSET / (20 × R_AC)",
        },
        "source": "SLUS892D p.17-18",
    }

    # 7. 安全定时
    timer_h = 5.0
    c_ttc_nf = timer_h * 60.0 / BQ24610_K_TTC_MIN_PER_NF
    result["charger_safety_timer"] = {
        "target_h": timer_h,
        "required_capacitance_nf": c_ttc_nf,
        "selected_capacitance_nf": 56.0,
        "actual_h": 56.0 * BQ24610_K_TTC_MIN_PER_NF / 60.0,
        "source": "SLUS892D p.18 Equation 6, K_TTC = 5.6 min/nF",
    }

    # 8. 电感与 LC
    ripple = inductor_design.calculate_ripple_for_inductance(
        18.0, CHARGE_TARGET_V, INDUCTANCE_H, 600e3
    )
    lc = inductor_design.calculate_lc_resonance(INDUCTANCE_H, OUTPUT_C_NOMINAL_F)
    dc_loss = inductor_design.estimate_inductor_dc_loss(SRN6045_220M_DCR, CHARGE_CURRENT_A)
    result["charger_inductor"] = {
        "part": "SRN6045-220M",
        "inductance_uh": INDUCTANCE_H * 1e6,
        **ripple,
        "ripple_ratio": ripple["estimated_ripple_a"] / CHARGE_CURRENT_A,
        "peak_current_a": CHARGE_CURRENT_A + ripple["estimated_ripple_a"] / 2.0,
        "isat_a": SRN6045_220M_ISAT,
        "irms_a": SRN6045_220M_IRMS,
        "dcr_ohm": SRN6045_220M_DCR,
        **dc_loss,
        "lc_resonance_khz": lc / 1000.0,
        "lc_resonance_target_khz": [12.0, 17.0],
        "lc_note": "标称 9.4 µF 得到 11.1 kHz，略低于 12–17 kHz；考虑 MLCC 直流偏压后有效电容下降，实际频率需实测，标记 NOT_VERIFIED",
        "source": "SLUS892D p.28-31",
    }

    # 9. 充电 FET 损耗
    duty = CHARGE_TARGET_V / 18.0
    high_side = duty * CHARGE_CURRENT_A ** 2 * CSD17578_RDS_MAX
    low_side = (1.0 - duty) * CHARGE_CURRENT_A ** 2 * CSD17581_RDS_MAX
    result["charger_mosfet_loss"] = {
        "duty": duty,
        "high_side_mosfet": "CSD17578Q5A",
        "high_side_conduction_w": high_side,
        "low_side_mosfet": "CSD17581Q5A",
        "low_side_conduction_w": low_side,
        "total_conduction_w": high_side + low_side,
        "switching_loss_status": "NOT_VERIFIED：需要实际驱动电流与 Qgd 波形，未做开关级联合仿真",
        "source": "SLUS892D p.29 Equation 18/22",
    }

    # 10. 铜箔
    result["copper_trace"] = {
        "example": "20 mm x 2 mm x 35 µm @ 2.5 A, 20 °C",
        **copper_calculations.calculate_copper_trace(20.0, 2.0, 35.0, 2.5, 20.0),
        "note": "理想均匀铜箔；不含过孔/焊点/缩颈/电流拥挤，不构成载流保证",
    }

    # 11. 汇总
    result["summary"] = {
        "shunt_selected_ohm": SENSE_R_OHM,
        "shunt_power_at_2p5a_w": next(
            c["power_loss_w"] for c in candidates if c["resistance_ohm"] == SENSE_R_OHM
        ),
        "bms_path_loss_w": bms_path["total_conduction_loss_w"],
        "charger_conduction_loss_w": high_side + low_side,
        "charge_voltage_actual_v": actual_v,
        "charge_current_actual_a": iset1_current,
        "precharge_current_actual_a": iset2_current,
        "input_current_limit_actual_a": acset_current,
        "balancing_worst_external_power_w": max(
            c["resistor_power_w"] for c in balancing
        ),
        "lc_resonance_khz": lc / 1000.0,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="第八阶段器件设计计算")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_id = _timestamp_run_id()
    output_dir = Path(args.output) if args.output else Path("results/eda") / f"run_calc_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    design = compute_design()
    design["run_id"] = run_id
    design["generated_at"] = datetime.now().isoformat(timespec="seconds")

    target = output_dir / "design_calculations.json"
    target.write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = design["summary"]
    print("设计计算完成（解析计算，非实测）")
    print(f"  输出: {target}")
    for key, value in summary.items():
        print(f"    {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

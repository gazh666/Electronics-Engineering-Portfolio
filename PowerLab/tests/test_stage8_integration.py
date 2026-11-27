"""第八阶段编排器纯逻辑测试（无 SPICE、不写 results/）。"""

from __future__ import annotations

from experiments import BudgetCounter
from validation.models import ValidationStatus
from validation.robustness_analysis import unavailable_design
from validation.validation_runner import (
    ALL_TASKS,
    PROFILES,
    build_acceptance,
    build_summary,
    credibility_matrix,
)


def _synthetic_outputs(*, include_tolerance: bool = True) -> dict:
    outputs = {
        "theory": {
            "case_count": 2,
            "theory_checks": [
                {
                    "check_id": "TH-VAL001-VOUT",
                    "case_id": "VAL001",
                    "metric_name": "output_voltage_mean_v",
                    "status": "PASS",
                },
                {
                    "check_id": "TH-VAL004-VOUT",
                    "case_id": "VAL004",
                    "metric_name": "output_voltage_mean_v",
                    "status": "FAIL",
                    "actual_value": 5.4,
                    "reference_value": 5.0,
                },
                {
                    "check_id": "TH-VAL005-VOUT",
                    "case_id": "VAL005",
                    "metric_name": "output_voltage_mean_v",
                    "status": "NOT_APPLICABLE",
                },
            ],
            "model_checks": [{"check_id": "XV-B-AVG", "status": "PASS"}],
            "cases": [
                {
                    "spice": {
                        "C": {"status": "COMPLETED", "data_source": "spice_simulation"},
                        "E": {"status": "COMPLETED", "data_source": "spice_simulation"},
                    }
                }
            ],
        },
        "convergence": {
            "analysis": {"overall_status": "NUMERICALLY_STABLE", "metrics": []},
            "convergence_orders": {"output_voltage_mean_v": 1.1},
        },
        "solver": {
            "summary": {"method_gear": "COMPLETED"},
            "runs": [{"status": "COMPLETED"}, {"status": "COMPLETED"}],
        },
        "conservation": {
            "result": {
                "status": "COMPLETED",
                "checks": [{"status": "PASS"} for _ in range(4)],
            }
        },
        "monte-carlo": {
            "profile": "smoke",
            "sampling": {"sample_count": 5},
            "records": [
                {"sample_id": f"mc-{index:03d}", "status": "COMPLETED", "metrics": {"output_voltage_mean_v": 5.0}}
                for index in range(1, 5)
            ]
            + [
                {
                    "sample_id": "mc-005",
                    "status": "ERROR",
                    "failure_reason": "synthetic transient failure",
                    "metrics": {},
                }
            ],
            "pass_ratio": {"all_samples": {"numerator": 4, "denominator": 5}},
            "statistics": {},
        },
        "robustness": {
            "designs": {
                "design_a": {"design": "nominal_design"},
                "design_b": unavailable_design("optimized_design", "stage6_missing"),
            },
            "closed_loop_screen": [{"corner": "nominal", "margin_status": "PASS"}],
            "closed_loop_screen_summary": {"evaluated": 1, "failed": 0},
            "closed_loop_spice_runs": [],
        },
    }
    if include_tolerance:
        outputs["tolerance"] = {
            "tolerances": {f"parameter_{index}": {} for index in range(6)},
            "rows": [],
            "first_order_propagation": {
                "metrics": {"output_voltage_mean_v": {"dominant_parameter": "inductance_h"}}
            },
        }
        outputs["corner"] = {
            "summary": {"evaluated_corners": 7},
            "corners": [{"corner": f"corner_{index}"} for index in range(7)],
        }
    return outputs


def _build(profile_tasks, outputs):
    budget = BudgetCounter(max_spice_runs=120)
    budget.add_spice(5)
    summary = build_summary("smoke", budget, outputs, list(profile_tasks))
    return summary, outputs


def test_profiles_are_consistent():
    assert len(ALL_TASKS) == 8
    assert set(PROFILES["smoke"]["tasks"]) <= set(PROFILES["standard"]["tasks"])
    assert set(PROFILES["standard"]["tasks"]) == set(ALL_TASKS)


def test_build_summary_preserves_fail_findings_and_failed_samples():
    summary, _ = _build(PROFILES["smoke"]["tasks"], _synthetic_outputs())
    failed = summary["theory"]["failed_checks"]
    assert len(failed) == 1
    assert failed[0]["status"] == "FAIL"
    assert failed[0]["check_id"] == "TH-VAL004-VOUT"
    assert summary["monte_carlo"]["sample_count"] == 5
    assert summary["monte_carlo"]["completed"] == 4
    assert summary["monte_carlo"]["states"] == {"COMPLETED": 4, "ERROR": 1}
    assert summary["tasks_completed"] == list(PROFILES["smoke"]["tasks"])
    assert summary["robustness"]["design_b"]["known_gaps"] == "stage6_missing"


def test_build_acceptance_skips_unrequested_tolerance_and_corner():
    summary, outputs = _build(PROFILES["smoke"]["tasks"], _synthetic_outputs())
    acceptance = build_acceptance(summary, outputs)
    by_id = {item["check_id"]: item for item in acceptance["checks"]}
    assert by_id["ACC-TOLERANCE"]["status"] == ValidationStatus.SKIP.value
    assert by_id["ACC-CORNER"]["status"] == ValidationStatus.SKIP.value
    assert by_id["ACC-ROBUSTNESS"]["status"] == ValidationStatus.PASS.value
    assert acceptance["findings"] == summary["theory"]["failed_checks"]


def test_build_acceptance_fails_when_requested_task_has_no_data():
    outputs = _synthetic_outputs(include_tolerance=False)
    summary, _ = _build(ALL_TASKS, outputs)
    acceptance = build_acceptance(summary, outputs)
    by_id = {item["check_id"]: item for item in acceptance["checks"]}
    assert by_id["ACC-TOLERANCE"]["status"] == ValidationStatus.FAIL.value
    assert by_id["ACC-CORNER"]["status"] == ValidationStatus.FAIL.value
    assert acceptance["overall_status"] == "PARTIAL_FAILURE"


def test_build_acceptance_marks_partial_failure_on_any_fail():
    outputs = _synthetic_outputs()
    summary, _ = _build(PROFILES["smoke"]["tasks"], outputs)
    summary["budget"]["spice_runs"] = summary["budget"]["max_spice_runs"] + 1
    acceptance = build_acceptance(summary, outputs)
    by_id = {item["check_id"]: item for item in acceptance["checks"]}
    assert by_id["ACC-BUDGET"]["status"] == ValidationStatus.FAIL.value
    assert acceptance["overall_status"] == "PARTIAL_FAILURE"


def test_credibility_matrix_has_four_sources():
    summary, _ = _build(PROFILES["smoke"]["tasks"], _synthetic_outputs())
    rows = credibility_matrix(summary)
    assert len(rows) == 4
    assert [row["data_source"] for row in rows] == [
        "analytical_theory",
        "averaged_model",
        "spice_simulation",
        "spice_derived",
    ]


def test_build_acceptance_completes_with_open_items_for_smoke():
    summary, outputs = _build(PROFILES["smoke"]["tasks"], _synthetic_outputs())
    acceptance = build_acceptance(summary, outputs)
    assert acceptance["overall_status"] == "COMPLETE_WITH_OPEN_ITEMS"
    assert acceptance["counts"].get("FAIL", 0) == 0

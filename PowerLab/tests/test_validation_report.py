"""第八阶段可信度报告渲染测试（无 SPICE、只写 tmp_path）。"""

from __future__ import annotations

import json

import pytest

import reports.validation_report as validation_report


def _synthetic_experiments(root):
    root.mkdir(parents=True, exist_ok=True)
    payloads = {
        "theoretical_comparison.json": {
            "cases": [
                {
                    "case": {"case_id": "VAL001"},
                    "theory": {
                        "ideal_ccm": {"ideal_output_voltage_v": 7.5},
                        "nonideal_ccm": {"output_voltage_v": 5.1},
                    },
                    "averaged_model": {"output_voltage_mean_v": 5.0},
                    "spice": {
                        "C": {"output_voltage_mean_v": 4.95},
                        "E": {"output_voltage_mean_v": 4.9},
                    },
                }
            ]
        },
        "timestep_convergence.json": {
            "runs": [
                {
                    "status": "COMPLETED",
                    "maximum_step_s": 200e-9,
                    "metrics": {
                        "output_voltage_mean_v": 4.90,
                        "output_voltage_ripple_vpp": 0.021,
                    },
                },
                {
                    "status": "COMPLETED",
                    "maximum_step_s": 100e-9,
                    "metrics": {
                        "output_voltage_mean_v": 4.95,
                        "output_voltage_ripple_vpp": 0.019,
                    },
                },
            ]
        },
        "tolerance.json": {
            "first_order_propagation": {
                "metrics": {
                    "output_voltage_mean_v": {
                        "contributions": {
                            "inductance_h": {"percent": 40.0},
                            "capacitance_f": {"percent": 60.0},
                        }
                    }
                }
            }
        },
        "corner.json": {
            "corners": [
                {"corner": "nominal", "metrics": {"output_voltage_mean_v": 5.0}},
                {"corner": "all_high", "metrics": {"output_voltage_mean_v": 5.05}},
            ]
        },
        "monte_carlo_standard.json": {
            "profile": "standard",
            "records": [
                {"status": "COMPLETED", "metrics": {"output_voltage_mean_v": value}}
                for value in (4.9, 5.0, 5.1)
            ],
        },
    }
    for name, payload in payloads.items():
        (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _synthetic_summary():
    return {
        "stage": 8,
        "profile": "standard",
        "tasks_requested": ["theory"],
        "tasks_completed": ["theory"],
        "budget": {"spice_runs": 12, "max_spice_runs": 120},
        "theory": {"case_count": 1, "check_counts": {"PASS": 3}, "failed_checks": []},
        "convergence": {"overall_status": "NUMERICALLY_STABLE", "metrics": [], "orders": {}},
        "solver": {"summary": {}, "run_count": 2},
        "conservation": {"status": "COMPLETED", "checks": []},
        "tolerance": {"parameter_count": 6, "row_count": 18, "dominant_parameters": {}},
        "corner": {"summary": {"evaluated_corners": 2}, "corners": []},
        "monte_carlo": {
            "profile": "standard",
            "sample_count": 3,
            "completed": 3,
            "states": {"COMPLETED": 3},
            "pass_ratio": {
                key: {
                    "numerator": 3,
                    "denominator": 30,
                    "wilson": {"lower": 0.05, "upper": 0.28},
                }
                for key in ("all_samples", "valid_samples", "numerical_valid")
            },
            "statistics": {},
        },
        "robustness": {"design_b": None, "screen_summary": None, "spice_runs": []},
        "acceptance": {
            "overall_status": "COMPLETE_WITH_OPEN_ITEMS",
            "checks": [
                {
                    "check_id": "ACC-THEORY-EXECUTED",
                    "description": "理论对照已执行",
                    "status": "PASS",
                    "evidence": "1 cases",
                }
            ],
            "findings": [],
        },
    }


def _credibility_rows():
    rows = []
    for evidence, source in (
        ("Ideal analytical formulas", "analytical_theory"),
        ("Averaged state-space", "averaged_model"),
        ("Switching SPICE (C/E)", "spice_simulation"),
        ("Monte Carlo statistics", "spice_derived"),
    ):
        rows.append(
            {
                "evidence": evidence,
                "data_source": source,
                "traceability": "trace",
                "physical_consistency": "NOT_APPLICABLE",
                "theory_consistency": "NOT_VERIFIED",
                "numerical_stability": "NOT_VERIFIED",
                "model_applicability": "scope",
                "parameter_robustness": "screened",
                "external_validation": "NOT_VERIFIED",
            }
        )
    return rows


@pytest.fixture()
def report_env(tmp_path, monkeypatch):
    experiments_root = tmp_path / "experiments"
    figures_root = tmp_path / "figures"
    _synthetic_experiments(experiments_root)
    (tmp_path / "credibility_matrix.json").write_text(
        json.dumps({"rows": _credibility_rows()}), encoding="utf-8"
    )
    monkeypatch.setattr(validation_report, "STAGE8_RESULTS_ROOT", tmp_path)
    monkeypatch.setattr(validation_report, "EXPERIMENTS_ROOT", experiments_root)
    monkeypatch.setattr(validation_report, "FIGURE_ROOT", figures_root)
    return tmp_path


def test_figure_functions_return_none_on_missing_data():
    assert validation_report.figure_theory(None) is None
    assert validation_report.figure_convergence({"runs": []}) is None
    assert validation_report.figure_tolerance(None) is None
    assert validation_report.figure_monte_carlo(None) is None
    assert validation_report.figure_corners(None) is None
    assert validation_report.figure_convergence({"runs": [{"status": "COMPLETED"}]}) is None


def test_figure_functions_write_into_figure_root(report_env):
    theory = json.loads((report_env / "experiments" / "theoretical_comparison.json").read_text())
    convergence = json.loads((report_env / "experiments" / "timestep_convergence.json").read_text())
    tolerance = json.loads((report_env / "experiments" / "tolerance.json").read_text())
    monte_carlo = json.loads((report_env / "experiments" / "monte_carlo_standard.json").read_text())
    corner = json.loads((report_env / "experiments" / "corner.json").read_text())

    paths = [
        validation_report.figure_theory(theory),
        validation_report.figure_convergence(convergence),
        validation_report.figure_tolerance(tolerance),
        validation_report.figure_monte_carlo(monte_carlo),
        validation_report.figure_corners(corner),
    ]
    assert all(path is not None and path.exists() for path in paths)
    assert all(path.parent == report_env / "figures" for path in paths)


def test_write_validation_report_contains_title_and_figure_references(report_env):
    target = validation_report.write_validation_report(
        _synthetic_summary(), report_env / "report.html"
    )
    html = target.read_text(encoding="utf-8")
    assert "PowerLab 第八阶段验证报告" in html
    for name in (
        "theory_comparison.png",
        "timestep_convergence.png",
        "tolerance_sensitivity.png",
        "monte_carlo_vout.png",
        "corner_comparison.png",
    ):
        assert name in html
        assert (report_env / "figures" / name).exists()
    assert "COMPLETE_WITH_OPEN_ITEMS" in html

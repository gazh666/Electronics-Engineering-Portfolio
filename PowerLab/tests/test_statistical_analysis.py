"""统计汇总、Wilson 区间、相关性与通过比例测试。"""

from __future__ import annotations

import math

import pytest

from validation.models import ValidationStatus
from validation.statistical_analysis import (
    evaluate_limit,
    pass_ratio_summary,
    pearson_correlation,
    rank_parameter_influence,
    spearman_correlation,
    summarize_metric,
    wilson_interval,
)


def test_summarize_metric_mean_std_percentiles():
    payload = summarize_metric([1.0, 2.0, 3.0, 4.0])
    assert payload["count"] == 4
    assert payload["mean"] == pytest.approx(2.5)
    assert payload["std"] == pytest.approx(math.sqrt(5.0 / 3.0), rel=1e-6)
    assert payload["minimum"] == pytest.approx(1.0)
    assert payload["maximum"] == pytest.approx(4.0)
    assert payload["p50"] == pytest.approx(2.5)
    assert payload["p5"] < payload["p95"]
    assert payload["status"] == "OK"


def test_summarize_metric_empty_is_insufficient_data():
    payload = summarize_metric([])
    assert payload == {"count": 0, "status": ValidationStatus.INSUFFICIENT_DATA.value}


def test_wilson_interval_known_value():
    payload = wilson_interval(27, 30)
    assert payload["status"] == "OK"
    assert payload["ratio"] == pytest.approx(0.9)
    assert payload["lower"] == pytest.approx(0.7438, abs=1e-3)
    assert payload["upper"] == pytest.approx(0.9654, abs=1e-3)


def test_wilson_interval_zero_total_has_no_bounds():
    payload = wilson_interval(0, 0)
    assert payload["status"] == ValidationStatus.INSUFFICIENT_DATA.value
    assert payload["lower"] is None
    assert payload["upper"] is None


def test_pearson_correlation_perfect_line():
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    y = [2.0 * value + 1.0 for value in x]
    payload = pearson_correlation(x, y)
    assert payload["status"] == "OK"
    assert payload["coefficient"] == pytest.approx(1.0)


def test_spearman_correlation_monotone_non_linear():
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    y = [value ** 3 for value in x]
    payload = spearman_correlation(x, y)
    assert payload["status"] == "OK"
    assert payload["coefficient"] == pytest.approx(1.0)


def test_evaluate_limit_min_and_max():
    rule = {"minimum": 4.8, "maximum": 5.2}
    assert evaluate_limit(5.0, rule) == ValidationStatus.PASS.value
    assert evaluate_limit(4.7, rule) == ValidationStatus.FAIL.value
    assert evaluate_limit(5.3, rule) == ValidationStatus.FAIL.value
    assert evaluate_limit(None, rule) == ValidationStatus.INSUFFICIENT_DATA.value


def test_pass_ratio_summary_three_denominators():
    samples = [
        {"sample_id": "mc-001", "status": "COMPLETED", "metrics": {"vout": 5.0}},
        {"sample_id": "mc-002", "status": "COMPLETED", "metrics": {"vout": 6.0}},
        {"sample_id": "mc-003", "status": "ERROR", "failure_reason": "synthetic"},
    ]
    payload = pass_ratio_summary(samples, metric_limit={"vout": {"minimum": 4.0, "maximum": 5.5}})
    assert payload["all_samples"]["denominator"] == 3
    assert payload["all_samples"]["numerator"] == 1
    assert payload["valid_samples"]["denominator"] == 2
    assert payload["valid_samples"]["numerator"] == 1
    assert payload["numerical_valid"]["denominator"] == 2
    assert payload["numerical_valid"]["numerator"] == 2
    assert payload["all_samples"]["wilson"]["lower"] is not None
    assert payload["all_samples"]["wilson"]["upper"] is not None


def test_rank_parameter_influence_orders_monotone_parameter_first():
    samples = [{"influential": i, "irrelevant": 5.0} for i in range(1, 7)]
    metrics = [{"vout": 2.0 * i} for i in range(1, 7)]
    ranking = rank_parameter_influence(samples, metrics, "vout")
    assert ranking[0]["parameter"] == "influential"
    assert ranking[0]["coefficient"] == pytest.approx(1.0)
    assert ranking[1]["parameter"] == "irrelevant"
    assert ranking[1]["coefficient"] is None
    assert ranking[1]["status"] == ValidationStatus.NOT_VERIFIED.value

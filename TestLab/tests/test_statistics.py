"""统计模块测试：空数据、单样本、多样本、非法值与分组。"""

import math

import pytest

from analysis.statistics import summarize, summarize_by_group, summarize_field


def test_empty_data_returns_none_statistics():
    result = summarize([])
    assert result["count"] == 0
    assert result["invalid_count"] == 0
    assert result["mean"] is None
    assert result["min"] is None
    assert result["max"] is None
    assert result["range"] is None
    assert result["median"] is None
    assert result["sample_std"] is None


def test_single_sample_has_no_sample_std():
    result = summarize([4.98])
    assert result["count"] == 1
    assert result["mean"] == pytest.approx(4.98)
    assert result["sample_std"] is None


def test_sample_statistics_match_manual_values():
    result = summarize([4.98, 5.00, 4.99])
    assert result["count"] == 3
    assert result["mean"] == pytest.approx(4.99)
    assert result["min"] == pytest.approx(4.98)
    assert result["max"] == pytest.approx(5.00)
    assert result["range"] == pytest.approx(0.02)
    assert result["median"] == pytest.approx(4.99)
    assert result["sample_std"] == pytest.approx(0.01)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, "abc", True, None])
def test_invalid_values_are_counted_not_crashing(value):
    result = summarize([5.0, value])
    assert result["count"] == 1
    assert result["invalid_count"] == 1


def test_all_invalid_returns_none_statistics():
    result = summarize(["abc", math.nan, None])
    assert result["count"] == 0
    assert result["invalid_count"] == 3
    assert result["mean"] is None


def test_summarize_field_ignores_missing_keys():
    records = [{"vout": 5.0}, {"vout": 4.9}, {"other": 1.0}]
    result = summarize_field(records, "vout")
    assert result["count"] == 2
    assert result["invalid_count"] == 1


def test_summarize_by_group_separates_operating_points():
    records = [
        {"load": 0.0, "vout": 5.0},
        {"load": 0.0, "vout": 5.0},
        {"load": 1.0, "vout": 4.98},
    ]
    grouped = summarize_by_group(records, "vout", ("load",))
    assert grouped[(0.0,)]["count"] == 2
    assert grouped[(0.0,)]["range"] == pytest.approx(0.0)
    assert grouped[(1.0,)]["mean"] == pytest.approx(4.98)

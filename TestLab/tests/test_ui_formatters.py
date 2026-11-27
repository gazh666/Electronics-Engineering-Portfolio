"""显示格式化测试：空值、单位、百分比与时间不产生误导性数字。"""

from __future__ import annotations

import math

from ui.formatters import (
    NONE_TEXT,
    format_bool,
    format_counts,
    format_duration_ms,
    format_fraction_percent,
    format_measurement,
    format_number,
    format_percent,
    format_source,
    format_timestamp,
    safe_float,
)


def test_none_and_non_numeric_become_na():
    assert format_number(None) == NONE_TEXT
    assert format_number("abc") == NONE_TEXT
    assert format_measurement(None, "V") == NONE_TEXT
    assert format_percent(None) == NONE_TEXT


def test_nan_and_infinity_are_not_displayed_as_numbers():
    assert format_number(math.nan) == NONE_TEXT
    assert format_number(math.inf) == NONE_TEXT
    assert format_number(-math.inf) == NONE_TEXT
    assert safe_float(math.nan) is None
    assert safe_float(True) is None


def test_number_and_unit_formatting():
    assert format_number(4.98765, 2) == "4.99"
    assert format_measurement(4.98765, "V", 3) == "4.988 V"
    assert format_measurement(1.0, "") == "1.000"


def test_percent_and_fraction_are_distinct():
    assert format_percent(90.0, 2) == "90.00 %"
    assert format_fraction_percent(0.9, 1) == "90.0 %"
    assert format_percent(0.9, 2) == "0.90 %"


def test_duration_switches_to_seconds():
    assert format_duration_ms(12.34) == "12.3 ms"
    assert format_duration_ms(1500) == "1.50 s"
    assert format_duration_ms(None) == NONE_TEXT


def test_timestamp_is_readable_and_keeps_invalid_text():
    assert format_timestamp("2026-11-24T08:00:00+00:00").startswith("2026-11-24")
    assert format_timestamp("not-a-time") == "not-a-time"
    assert format_timestamp(None) == NONE_TEXT


def test_bool_formatting_requires_real_bool():
    assert format_bool(True) == "是"
    assert format_bool(False) == "否"
    assert format_bool("true") == NONE_TEXT


def test_source_labels():
    assert format_source("behavioral_model") == "DUT 行为模型"
    assert format_source("fault_injected_model") == "故障注入视图"
    assert format_source("static_mock") == "DMM 固定模拟值"
    assert format_source(None) == NONE_TEXT


def test_counts_formatting():
    assert format_counts({"PASS": 2, "FAIL": 1}) == "PASS 2 / FAIL 1 / ERROR 0 / SKIP 0"
    assert format_counts(None) == "PASS 0 / FAIL 0 / ERROR 0 / SKIP 0"

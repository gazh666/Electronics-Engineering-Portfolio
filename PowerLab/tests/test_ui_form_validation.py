"""表单校验测试（第九阶段 Task 5、16）。

用轻量假 st 模块替换 Streamlit 组件，直接验证表单的跨字段校验逻辑；
表单值保持工程单位，SI 转换由 jobs.registry 负责。
"""

from __future__ import annotations

import contextlib

import pytest

from ui import form_validation


class _FakeSt:
    def __init__(self, overrides: dict | None = None) -> None:
        self.overrides = overrides or {}

    def columns(self, count):
        return [contextlib.nullcontext() for _ in range(count)]

    def number_input(
        self,
        label,
        min_value=None,
        max_value=None,
        value=None,
        step=None,
        format=None,
        help=None,
        key=None,
    ):
        return self.overrides.get(key, value)

    def selectbox(self, label, options, **kwargs):
        return options[kwargs.get("index", 0)]

    def radio(self, label, options, **kwargs):
        return options[0]

    def checkbox(self, label, value=False, **kwargs):
        return value

    def text_input(self, label, value="", **kwargs):
        return self.overrides.get(kwargs.get("key"), value)

    def caption(self, *args, **kwargs):
        return None


@pytest.fixture
def fake_st(monkeypatch):
    def _install(overrides: dict | None = None) -> _FakeSt:
        fake = _FakeSt(overrides)
        monkeypatch.setattr(form_validation, "st", fake)
        return fake

    return _install


def test_model_form_defaults_are_engineering_units(fake_st):
    fake_st()
    values, errors = form_validation.model_form("nonideal_buck", key_prefix="m")
    assert errors == []
    assert values["end_time_s"] == pytest.approx(5.0)  # ms
    assert values["step_time_s"] == pytest.approx(100.0)  # ns
    assert values["inductance_h"] == pytest.approx(47.0)  # uH


def test_model_form_rejects_max_step_above_step(fake_st):
    fake_st({"m_max_step_time_s": 200.0})
    _, errors = form_validation.model_form("nonideal_buck", key_prefix="m")
    assert any("最大步长" in item for item in errors)


def test_model_form_rejects_buck_target_above_input(fake_st):
    fake_st({"b_target_output_voltage_v": 12.0, "b_input_voltage_v": 12.0})
    _, errors = form_validation.model_form("buck_ideal", key_prefix="b")
    assert any("目标输出电压" in item for item in errors)


def test_model_form_voltage_divider_has_no_cross_checks(fake_st):
    fake_st()
    values, errors = form_validation.model_form("voltage_divider", key_prefix="d")
    assert errors == []
    assert values["vin_v"] == pytest.approx(12.0)


def test_sweep_form_parses_commas(fake_st):
    fake_st({"s_values": "22, 47，100"})
    payload = form_validation.sweep_form(key_prefix="s")
    assert payload["parameter"] == "inductance_h"
    assert payload["values"] == [22.0, 47.0, 100.0]
    assert payload["errors"] == []


def test_sweep_form_reports_parse_error(fake_st):
    fake_st({"s_values": "22, abc"})
    payload = form_validation.sweep_form(key_prefix="s")
    assert any("无法解析" in item for item in payload["errors"])


def test_sweep_form_requires_two_values(fake_st):
    fake_st({"s_values": "47"})
    payload = form_validation.sweep_form(key_prefix="s")
    assert any("至少需要两个" in item for item in payload["errors"])


def test_sweep_form_limits_value_count(fake_st):
    fake_st({"s_values": ",".join(str(index) for index in range(1, 42))})
    payload = form_validation.sweep_form(key_prefix="s")
    assert any("40" in item for item in payload["errors"])


def test_sweep_form_rejects_negative_values(fake_st):
    fake_st({"s_values": "-1, 2"})
    payload = form_validation.sweep_form(key_prefix="s")
    assert any("正数" in item for item in payload["errors"])


def test_validation_form_defaults(fake_st):
    fake_st()
    payload = form_validation.validation_form(key_prefix="v")
    assert payload["steps_ns"] == [200.0, 100.0, 50.0]
    assert payload["errors"] == []
    assert payload["variant"] == "E"


def test_validation_form_rejects_out_of_range_step(fake_st):
    fake_st({"v_steps": "200, 6000"})
    payload = form_validation.validation_form(key_prefix="v")
    assert any("5–5000" in item for item in payload["errors"])


def test_validation_form_rejects_single_step(fake_st):
    fake_st({"v_steps": "100"})
    payload = form_validation.validation_form(key_prefix="v")
    assert any("至少需要两个" in item for item in payload["errors"])


def test_closed_loop_form_defaults(fake_st):
    fake_st()
    payload = form_validation.closed_loop_form(key_prefix="c")
    assert payload["errors"] == []
    assert payload["mode"] == "closed_loop"
    assert payload["end_time_ms"] == pytest.approx(8.0)


def test_closed_loop_form_rejects_bad_duty_limits(fake_st):
    fake_st({"c_dmin": 0.95})
    payload = form_validation.closed_loop_form(key_prefix="c")
    assert any("占空比下限" in item for item in payload["errors"])


def test_closed_loop_form_rejects_step_order(fake_st):
    fake_st({"c_max": 200.0})
    payload = form_validation.closed_loop_form(key_prefix="c")
    assert any("最大步长" in item for item in payload["errors"])


def test_monte_carlo_form_returns_fraction_tolerances(fake_st):
    fake_st()
    payload = form_validation.monte_carlo_form(key_prefix="mc")
    assert payload["samples"] == 5
    assert payload["tolerances"]["inductor"] == pytest.approx(0.1)
    assert payload["errors"] == []


def test_monte_carlo_form_keeps_seed(fake_st):
    fake_st({"mc_seed": 42})
    payload = form_validation.monte_carlo_form(key_prefix="mc")
    assert payload["seed"] == 42

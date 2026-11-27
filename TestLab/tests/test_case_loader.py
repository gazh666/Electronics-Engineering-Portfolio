"""测试用例/方案加载器测试：全部使用临时 YAML，不接触仪器。"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from engine.case_loader import load_test_cases, load_test_suites

ROOT = Path(__file__).resolve().parents[1]


def _case(**overrides) -> dict:
    case = {
        "id": "TC900",
        "name": "临时用例",
        "category": "normal",
        "vin": 12.0,
        "input_current_limit": 3.0,
        "load_current": 1.0,
        "expected_state": "NORMAL",
        "limits": {"vout": {"min": 4.9, "max": 5.1}},
    }
    case.update(overrides)
    return case


def _write(tmp_path: Path, payload: dict, name: str = "cases.yaml") -> Path:
    path = tmp_path / name
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _payload(*cases: dict, version="1.0", **extra) -> dict:
    payload = {"version": version, "test_cases": list(cases)}
    payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# 真实配置
# ---------------------------------------------------------------------------


def test_real_test_cases_load():
    cases = load_test_cases(ROOT / "configs" / "test_cases.yaml")
    assert len(cases) == 12
    assert [case.case_id for case in cases][:3] == ["TC001", "TC002", "TC003"]
    first = cases[0]
    assert first.expected_state == "NORMAL"
    assert first.limits["vout"] == {"min": 4.9, "max": 5.1}
    assert first.limits["efficiency_percent"]["min"] == 85.0


def test_real_test_suites_reference_existing_cases():
    cases = load_test_cases(ROOT / "configs" / "test_cases.yaml")
    suites = load_test_suites(
        ROOT / "configs" / "test_suites.yaml",
        [case.case_id for case in cases],
    )
    assert {suite.suite_id for suite in suites} == {
        "SUITE-SMOKE",
        "SUITE-PROTECTION",
        "SUITE-REGRESSION",
        # 阶段八验收使用的普通回归方案（不加载故障场景）
        "SUITE005",
    }
    regression = next(suite for suite in suites if suite.suite_id == "SUITE-REGRESSION")
    assert len(regression.case_ids) == 12
    assert regression.stop_on_fail is False
    stage8 = next(suite for suite in suites if suite.suite_id == "SUITE005")
    assert stage8.case_ids == ("TC001", "TC002", "TC003", "TC011", "TC012")


def test_real_engine_validation_configs_load():
    cases = load_test_cases(ROOT / "configs" / "engine_validation_cases.yaml")
    suites = load_test_suites(
        ROOT / "configs" / "engine_validation_suites.yaml",
        [case.case_id for case in cases],
    )
    assert [case.case_id for case in cases] == ["EV001", "EV002", "EV003", "EV004"]
    assert cases[2].enabled is False
    assert suites[0].suite_id == "SUITE-EV"


# ---------------------------------------------------------------------------
# 用例文件校验
# ---------------------------------------------------------------------------


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_test_cases("不存在的文件.yaml")


def test_missing_version_rejected(tmp_path):
    path = _write(tmp_path, {"test_cases": [_case()]})
    with pytest.raises(ValueError, match="version"):
        load_test_cases(path)


def test_unsupported_version_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(), version="2.0"))
    with pytest.raises(ValueError, match="版本不受支持"):
        load_test_cases(path)


def test_unknown_top_level_key_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(), defualts={}))
    with pytest.raises(ValueError, match="未知字段"):
        load_test_cases(path)


def test_empty_test_cases_rejected(tmp_path):
    path = _write(tmp_path, _payload())
    with pytest.raises(ValueError, match="不能为空"):
        load_test_cases(path)


def test_missing_required_field_rejected(tmp_path):
    case = _case()
    del case["load_current"]
    path = _write(tmp_path, _payload(case))
    with pytest.raises(ValueError, match="load_current"):
        load_test_cases(path)


def test_duplicate_case_id_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(), _case(name="重复")))
    with pytest.raises(ValueError, match="重复的用例编号"):
        load_test_cases(path)


def test_unknown_case_field_rejected(tmp_path):
    # 典型错误：沿用旧版 voltage_min/voltage_max 字段
    path = _write(tmp_path, _payload(_case(voltage_min=4.9)))
    with pytest.raises(ValueError, match="未知字段"):
        load_test_cases(path)


def test_boolean_numeric_field_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(vin=True)))
    with pytest.raises(ValueError, match="布尔"):
        load_test_cases(path)


def test_non_finite_numeric_field_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(vin=math.nan)))
    with pytest.raises(ValueError, match="有限"):
        load_test_cases(path)


def test_out_of_range_voltage_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(vin=35.0)))
    with pytest.raises(ValueError, match="超出允许范围"):
        load_test_cases(path)


def test_out_of_range_load_current_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(load_current=9.0)))
    with pytest.raises(ValueError, match="超出允许范围"):
        load_test_cases(path)


def test_invalid_expected_state_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(expected_state="BROKEN")))
    with pytest.raises(ValueError, match="expected_state"):
        load_test_cases(path)


def test_string_boolean_rejected(tmp_path):
    # YAML 中写成字符串 "false" 必须报错，不能当作 True
    path = _write(tmp_path, _payload(_case(enabled="false")))
    with pytest.raises(ValueError, match="布尔值"):
        load_test_cases(path)


def test_unknown_limit_metric_rejected(tmp_path):
    path = _write(
        tmp_path,
        _payload(_case(limits={"output_voltage": {"min": 4.9, "max": 5.1}})),
    )
    with pytest.raises(ValueError, match="未知指标"):
        load_test_cases(path)


def test_limit_requires_min_and_max(tmp_path):
    path = _write(tmp_path, _payload(_case(limits={"vout": {"min": 4.9}})))
    with pytest.raises(ValueError, match="min 与 max"):
        load_test_cases(path)


def test_limit_min_greater_than_max_rejected(tmp_path):
    path = _write(tmp_path, _payload(_case(limits={"vout": {"min": 5.1, "max": 4.9}})))
    with pytest.raises(ValueError, match="不能大于"):
        load_test_cases(path)


def test_limit_unknown_bound_key_rejected(tmp_path):
    path = _write(
        tmp_path,
        _payload(_case(limits={"vout": {"min": 4.9, "max": 5.1, "typ": 5.0}})),
    )
    with pytest.raises(ValueError, match="未知字段"):
        load_test_cases(path)


def test_valid_case_defaults_applied(tmp_path):
    path = _write(tmp_path, _payload(_case()))
    (case,) = load_test_cases(path)
    assert case.output_enabled is True
    assert case.load_enabled is True
    assert case.enabled is True


# ---------------------------------------------------------------------------
# 测试方案校验
# ---------------------------------------------------------------------------


def _suite_payload(*suites: dict, version="1.0") -> dict:
    return {"version": version, "test_suites": list(suites)}


def _suite(**overrides) -> dict:
    suite = {"id": "S1", "name": "临时方案", "cases": ["TC900"]}
    suite.update(overrides)
    return suite


def test_suite_unknown_case_reference_rejected(tmp_path):
    path = _write(tmp_path, _suite_payload(_suite(cases=["TC999"])), "suites.yaml")
    with pytest.raises(ValueError, match="不存在的用例"):
        load_test_suites(path, ["TC900"])


def test_suite_empty_cases_rejected(tmp_path):
    path = _write(tmp_path, _suite_payload(_suite(cases=[])), "suites.yaml")
    with pytest.raises(ValueError, match="非空列表"):
        load_test_suites(path, ["TC900"])


def test_suite_duplicate_case_reference_rejected(tmp_path):
    path = _write(
        tmp_path,
        _suite_payload(_suite(cases=["TC900", "TC900"])),
        "suites.yaml",
    )
    with pytest.raises(ValueError, match="重复引用"):
        load_test_suites(path, ["TC900"])


def test_duplicate_suite_id_rejected(tmp_path):
    path = _write(
        tmp_path,
        _suite_payload(_suite(), _suite(name="重复方案")),
        "suites.yaml",
    )
    with pytest.raises(ValueError, match="重复的测试方案编号"):
        load_test_suites(path, ["TC900"])


def test_suite_unknown_field_rejected(tmp_path):
    path = _write(
        tmp_path,
        _suite_payload(_suite(stop_on_failure=True)),
        "suites.yaml",
    )
    with pytest.raises(ValueError, match="未知字段"):
        load_test_suites(path, ["TC900"])


def test_suite_string_boolean_rejected(tmp_path):
    path = _write(
        tmp_path,
        _suite_payload(_suite(stop_on_fail="yes")),
        "suites.yaml",
    )
    with pytest.raises(ValueError, match="布尔值"):
        load_test_suites(path, ["TC900"])


def test_suite_defaults(tmp_path):
    path = _write(tmp_path, _suite_payload(_suite()), "suites.yaml")
    (suite,) = load_test_suites(path, ["TC900"])
    assert suite.stop_on_fail is False
    assert suite.stop_on_error is True
    assert suite.case_ids == ("TC900",)

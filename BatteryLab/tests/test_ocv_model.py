"""OCV 模型测试。"""

from __future__ import annotations

import pytest

from battery_models.ocv_model import (
    ConstantOcvModel,
    OcvError,
    TableOcvModel,
    interpolate_ocv,
    load_ocv_reference,
)


def test_constant_ocv_is_soc_independent() -> None:
    model = ConstantOcvModel(3.8)
    assert model.voltage(0.0) == pytest.approx(3.8)
    assert model.voltage(0.6) == pytest.approx(3.8)
    assert model.voltage(1.0) == pytest.approx(3.8)
    assert model.metadata()["ocv_model"] == "constant_ocv_benchmark"


def test_table_interpolation_values() -> None:
    model = load_ocv_reference()
    assert model.voltage(0.0) == pytest.approx(3.00)
    assert model.voltage(0.1) == pytest.approx(3.35)
    assert model.voltage(0.3) == pytest.approx(3.60)
    assert model.voltage(0.6) == pytest.approx(3.80)
    assert model.voltage(1.0) == pytest.approx(4.20)
    assert model.source_type == "educational_assumption"


def test_interpolate_function_matches_model() -> None:
    model = load_ocv_reference()
    assert interpolate_ocv(0.75, model.soc_table, model.ocv_table) == pytest.approx(model.voltage(0.75))


@pytest.mark.parametrize("soc", [-0.1, 1.1, float("nan")])
def test_soc_out_of_range_rejected(soc: float) -> None:
    model = load_ocv_reference()
    with pytest.raises(OcvError):
        model.voltage(soc)


def test_invalid_tables_rejected() -> None:
    with pytest.raises(OcvError):
        TableOcvModel((0.0, 0.5, 1.0), (3.0, 3.6))
    with pytest.raises(OcvError):
        TableOcvModel((0.0, 0.6, 0.4, 1.0), (3.0, 3.6, 3.7, 4.2))
    with pytest.raises(OcvError):
        TableOcvModel((0.1, 0.5, 0.9), (3.2, 3.6, 4.0))
    with pytest.raises(OcvError):
        TableOcvModel((0.0, 1.0), (3.0, float("inf")))

"""辨识参数数据结构、边界校验与冻结/读取。"""

from __future__ import annotations

import numpy as np
import pytest

from battery_models.ocv_model import IdentifiedOcvModel
from identification.models import IdentificationError, IdentifiedECMParameters
from identification.parameter_store import freeze_model, load_frozen_model
from identification.parameter_validator import identifiability_report, validate_parameters


def test_parameter_validation_rules():
    with pytest.raises(IdentificationError):
        IdentifiedECMParameters(model_order=1, capacity_ah=2.0, r0_ohm=-0.01, r1_ohm=0.01, tau1_s=50.0)
    with pytest.raises(IdentificationError):
        IdentifiedECMParameters(model_order=2, capacity_ah=2.0, r0_ohm=0.03, r1_ohm=0.01, tau1_s=200.0, r2_ohm=0.01, tau2_s=100.0)
    with pytest.raises(IdentificationError):
        IdentifiedECMParameters(
            model_order=1, capacity_ah=2.0, r0_ohm=0.03, r1_ohm=0.01, tau1_s=50.0, c1_f=999.0
        )


def test_from_time_constants_sorts():
    parameters = IdentifiedECMParameters.from_time_constants(
        model_order=2,
        capacity_ah=2.0,
        r0_ohm=0.03,
        time_constants_s=[1200.0, 50.0],
        resistances_ohm=[0.02, 0.01],
    )
    assert parameters.tau1_s == 50.0
    assert parameters.tau2_s == 1200.0
    assert parameters.branches()[0].resistance_ohm == 0.01


def test_as_definition_roundtrip():
    parameters = IdentifiedECMParameters.from_time_constants(
        model_order=2,
        capacity_ah=2.03,
        r0_ohm=0.05,
        time_constants_s=[80.0, 2000.0],
        resistances_ohm=[0.012, 0.018],
    )
    definition = parameters.as_definition()
    assert definition.order == 2
    assert definition.parameters.capacity_ah == pytest.approx(2.03)
    assert definition.parameters.parameter_source == "identified_parameters"


def test_freeze_and_load(tmp_path):
    parameters = IdentifiedECMParameters.from_time_constants(
        model_order=2,
        capacity_ah=2.03,
        r0_ohm=0.05,
        time_constants_s=[80.0, 2000.0],
        resistances_ohm=[0.012, 0.018],
        cell_id="SP2",
        temperature_c=25.0,
    )
    ocv = IdentifiedOcvModel(tuple(np.linspace(0, 1, 5)), tuple(np.linspace(3.0, 4.15, 5)))
    paths = freeze_model(
        "unit_test",
        parameters,
        ocv,
        training_manifest={"initial_soc_method": "recorded_capacity_balance"},
        fitting_config={"profile": "unit"},
        parameter_quality={"status": "IDENTIFIED"},
        root=tmp_path,
    )
    assert "metadata" in paths
    loaded = load_frozen_model("unit_test", root=tmp_path)
    assert loaded["parameters"].r0_ohm == pytest.approx(0.05)
    assert loaded["ocv_model"].voltage(1.0) == pytest.approx(4.15)
    with pytest.raises(IdentificationError):
        freeze_model("unit_test", parameters, ocv, training_manifest={}, fitting_config={}, parameter_quality={}, root=tmp_path)


def test_validate_and_identifiability():
    parameters = IdentifiedECMParameters.from_time_constants(
        model_order=1,
        capacity_ah=2.0,
        r0_ohm=0.03,
        time_constants_s=[50.0],
        resistances_ohm=[0.01],
    )
    report = validate_parameters(parameters, {"r0_ohm": (0.03, 0.15), "r1_ohm": (0.001, 0.08), "tau1_s": (5.0, 300.0)})
    assert report["status"] == "BOUND_LIMITED"
    assert "r0_ohm_lower" in report["boundary_issues"]
    identifiability = identifiability_report(np.array([[1.0, 0.0], [0.0, 1.0]]), ["a", "b"])
    assert identifiability["available"]
    assert identifiability["condition_number"] == pytest.approx(1.0)

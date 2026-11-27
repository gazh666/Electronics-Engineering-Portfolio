"""环境与后端真实性测试。"""

from __future__ import annotations

import sys

import numpy as np
import pytest


def test_python_version():
    assert sys.version_info[:2] == (3, 11)


def test_core_packages_import():
    import matplotlib  # noqa: F401
    import openpyxl  # noqa: F401
    import pandas  # noqa: F401
    import pybamm
    import scipy  # noqa: F401

    assert pybamm.__version__


def test_pybamm_real_solve_finite():
    import pybamm

    model = pybamm.lithium_ion.SPM()
    solution = pybamm.Simulation(model).solve([0, 30])
    voltage = np.asarray(solution["Voltage [V]"].entries, dtype=float)
    assert len(voltage) > 1
    assert np.isfinite(voltage).all()
    assert 3.0 < voltage[0] < 4.5


def test_ngspice_real_divider():
    pytest.importorskip("PySpice")
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_V, u_kOhm

    try:
        circuit = Circuit("divider")
        circuit.V("input", "vin", circuit.gnd, 5 @ u_V)
        circuit.R(1, "vin", "out", 10 @ u_kOhm)
        circuit.R(2, "out", circuit.gnd, 10 @ u_kOhm)
        analysis = circuit.simulator(temperature=25, nominal_temperature=25).operating_point()
    except Exception as exc:  # noqa: BLE001 - 后端不可用时保留明确未验证状态
        pytest.skip(f"ngspice 后端不可用: {exc}")
    assert float(analysis["out"][0]) == pytest.approx(2.5, abs=1e-6)

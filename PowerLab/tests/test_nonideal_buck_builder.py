"""五模型电路构建器测试（网表结构，不运行 SPICE）。"""

from __future__ import annotations

import re

import pytest

from circuits.nonideal_buck import (
    VARIANT_TABLE,
    build_nonideal_buck,
    get_variant_features,
    variant_description,
)
from circuits.nonideal_config import load_nonideal_buck_config


def _netlist(variant: str) -> str:
    return str(build_nonideal_buck(load_nonideal_buck_config(), variant))


def _has(netlist: str, pattern: str) -> bool:
    return re.search(pattern, netlist, flags=re.MULTILINE) is not None


def test_variant_table_covers_a_to_e():
    assert tuple(sorted(VARIANT_TABLE)) == ("A", "B", "C", "D", "E")
    assert get_variant_features("E").uses_parasitic_capacitors is True
    assert get_variant_features("A").uses_mosfet is False
    assert "baseline" in variant_description("A")
    with pytest.raises(ValueError):
        get_variant_features("Z")


def test_model_a_reuses_stage3_switch_baseline():
    netlist = _netlist("A")
    assert "SWMOD" in netlist
    assert _has(netlist, r"^S1\s+vin\s+sw\s+gate\s+0\s+SWMOD")
    assert "NMOS_EDU" not in netlist
    assert "VDRV" not in netlist


def test_model_b_adds_passive_parasitics_only():
    netlist = _netlist("B")
    assert _has(netlist, r"^RDCR\s+l_dcr\s+out")
    assert _has(netlist, r"^RESR\s+c_esr\s+cap_internal")
    assert "NMOS_EDU" not in netlist
    assert "DFREE_NONIDEAL" not in netlist


def test_model_c_uses_nonideal_diode():
    netlist = _netlist("C")
    assert _has(netlist, r"^DFREE\s+diode_a\s+sw\s+DFREE_NONIDEAL")
    assert "SWMOD" in netlist
    assert "NMOS_EDU" not in netlist


def test_model_d_uses_nmos_and_floating_driver():
    netlist = _netlist("D")
    assert _has(netlist, r"^M1\s+drain\s+gate\s+sw\s+sw\s+NMOS_EDU")
    assert _has(netlist, r"^VDRV\s+drv\s+sw\s+")
    assert _has(netlist, r"^RG\s+drv\s+gate\s+")
    assert "CGS" not in netlist
    assert "SWMOD" not in netlist


def test_model_e_adds_parasitic_capacitors():
    netlist = _netlist("E")
    assert _has(netlist, r"^CGS\s+gate\s+sw\s+")
    assert _has(netlist, r"^CGD\s+gate\s+drain\s+")
    assert _has(netlist, r"^CDS\s+drain\s+sw\s+")


def test_sense_sources_are_present_in_measured_variants():
    for variant in ("B", "C", "D", "E"):
        netlist = _netlist(variant)
        for element in ("VIN", "VDSENSE", "VLSENSE", "VCSENSE"):
            assert _has(netlist, rf"^{element}\b"), f"{element} missing in {variant}"


def test_title_and_invalid_arguments():
    config = load_nonideal_buck_config()
    with pytest.raises(ValueError):
        build_nonideal_buck("bad")
    with pytest.raises(ValueError):
        build_nonideal_buck(config, title="  ")
    netlist = str(build_nonideal_buck(config, "E", title="Custom title"))
    assert netlist.splitlines()[0].strip() == ".title Custom title - Model E"

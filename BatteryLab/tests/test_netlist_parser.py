import pytest

from eda_tools.netlist_parser import parse_kicad_xml_netlist, summarize_netlist

FIXTURE = """
<export>
  <components>
    <comp ref="R1"><value>10k</value><footprint>Test:R</footprint></comp>
    <comp ref="U1"><value>AFE</value><footprint>Test:QFN</footprint></comp>
  </components>
  <nets>
    <net code="1" name="GND">
      <node ref="R1" pin="2"/>
      <node ref="U1" pin="10"/>
    </net>
    <net code="2" name="CELL_0_POS">
      <node ref="R1" pin="1"/>
      <node ref="U1" pin="8" pinfunction="VC1"/>
    </net>
  </nets>
</export>
"""


def test_parse_netlist(tmp_path):
    fixture = tmp_path / "test.xml"
    fixture.write_text(FIXTURE, encoding="utf-8")

    result = parse_kicad_xml_netlist(fixture)

    assert result["pin_to_net"][("R1", "2")] == "GND"
    assert result["pin_to_net"][("U1", "8")] == "CELL_0_POS"
    assert result["components"]["U1"]["footprint"] == "Test:QFN"
    assert len(result["nets"]) == 2


def test_summarize_netlist(tmp_path):
    fixture = tmp_path / "test.xml"
    fixture.write_text(FIXTURE, encoding="utf-8")
    summary = summarize_netlist(parse_kicad_xml_netlist(fixture))
    assert summary["component_count"] == 2
    assert summary["net_count"] == 2
    assert summary["single_pin_net_count"] == 0


def test_duplicate_reference(tmp_path):
    fixture = tmp_path / "dup.xml"
    fixture.write_text(
        """
        <export><components>
          <comp ref="R1"><value>1k</value></comp>
          <comp ref="R1"><value>2k</value></comp>
        </components><nets><net name="GND"><node ref="R1" pin="1"/></net></nets></export>
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate reference"):
        parse_kicad_xml_netlist(fixture)


def test_pin_in_two_nets(tmp_path):
    fixture = tmp_path / "multi.xml"
    fixture.write_text(
        """
        <export><components><comp ref="R1"><value>1k</value></comp></components>
        <nets>
          <net name="A"><node ref="R1" pin="1"/></net>
          <net name="B"><node ref="R1" pin="1"/></net>
        </nets></export>
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Pin in multiple nets"):
        parse_kicad_xml_netlist(fixture)


def test_empty_components_rejected(tmp_path):
    fixture = tmp_path / "empty.xml"
    fixture.write_text(
        "<export><components/><nets><net name='GND'/></nets></export>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Empty component list"):
        parse_kicad_xml_netlist(fixture)


def test_unexpected_structure_rejected(tmp_path):
    fixture = tmp_path / "bad.xml"
    fixture.write_text("<export><foo/></export>", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected netlist format"):
        parse_kicad_xml_netlist(fixture)


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_kicad_xml_netlist(tmp_path / "missing.xml")

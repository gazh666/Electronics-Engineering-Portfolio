"""生成 BatteryLab_BMS_V1 / BatteryLab_Charger_V1 的真实可编辑 KiCad 原理图。

- 使用已安装 KiCad 10 的官方符号库提取标准器件符号；
- BQ76922 / BQ24610 / SON5x6 NMOS 使用按官方引脚表构建的自定义符号；
- 连接关系用全局标签表达，网名与 hardware/eda/requirements/*.csv 完全一致；
- TS2/PDSG/PCHG 按数据手册允许悬空，放置 no_connect；
- 只生成原理图与工程文件，不伪造 ERC/DRC/PCB。

运行：
    python -B -m scripts.build_eda_schematic
"""

from __future__ import annotations

import csv
import json
import re
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYM_DIR = Path(r"C:\\Users\\<user>\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols")
EDA = PROJECT_ROOT / "hardware" / "eda"
REQ = EDA / "requirements"

uid = lambda: str(uuid.uuid4())
CUSTOM_LIB: dict[str, str] = {}


# ---------------------------------------------------------------- S-expr utils
def extract_balanced(s: str, start: int) -> str:
    depth = 0
    i = start
    in_str = False
    while i < len(s):
        ch = s[i]
        if in_str:
            if ch == '"' and s[i - 1] != "\\":
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        i += 1
    raise ValueError("unbalanced")


def lib_symbol_block(lib: str, name: str) -> str:
    text = (SYM_DIR / f"{lib}.kicad_sym").read_text(encoding="utf-8")
    m = re.search(r'\(symbol "%s"' % re.escape(name), text)
    if not m:
        raise SystemExit(f"symbol not found: {lib}:{name}")
    block = extract_balanced(text, m.start())
    return block.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


def symbol_pins(block: str) -> list[tuple[str, str, float, float, float]]:
    pins = []
    for pm in re.finditer(r"\(pin\b", block):
        seg = extract_balanced(block, pm.start())
        at = re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)", seg)
        num = re.search(r'\(number\s+"([^"]+)"', seg)
        nm = re.search(r'\(name\s+"([^"]*)"', seg)
        if at and num:
            pins.append((num.group(1), nm.group(1) if nm else "", float(at.group(1)), float(at.group(2)), float(at.group(3))))
    return pins


# ---------------------------------------------------------------- custom IC symbol
def make_ic_symbol(lib_id: str, value: str, pins: list[tuple[str, str]], footprint: str,
                   datasheet: str, description: str, pitch: float = 2.54, width: float = 30.48) -> tuple[str, dict]:
    """pins: list of (number, name). Thermal pad number 'PAD' placed bottom."""
    body_pins = [(n, nm) for (n, nm) in pins if n != "PAD"]
    pad_pins = [(n, nm) for (n, nm) in pins if n == "PAD"]
    half = (len(body_pins) + 1) // 2
    left = body_pins[:half]
    right = body_pins[half:]
    rows = max(len(left), len(right))
    height = (rows + 1) * pitch
    top = (rows - 1) / 2 * pitch
    pin_len = 2.54
    lib = lib_id.split(":")[0]
    name = lib_id.split(":")[1]

    lines = [f'\t\t(symbol "{lib}:{name}"',
             "\t\t\t(pin_names", "\t\t\t\t(offset 1.016)", "\t\t\t)",
             "\t\t\t(exclude_from_sim no)", "\t\t\t(in_bom yes)", "\t\t\t(on_board yes)",
             f'\t\t\t(property "Reference" "U"\n\t\t\t\t(at {-width/2 - 5.08} {height/2 + 2.54} 0)\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t)\n\t\t\t\t\t(justify left)\n\t\t\t\t)\n\t\t\t)',
             f'\t\t\t(property "Value" "{value}"\n\t\t\t\t(at {-width/2 - 5.08} {height/2} 0)\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t)\n\t\t\t\t\t(justify left)\n\t\t\t\t)\n\t\t\t)',
             f'\t\t\t(property "Footprint" "{footprint}"\n\t\t\t\t(at 0 0 0)\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t)\n\t\t\t\t\t(hide yes)\n\t\t\t\t)\n\t\t\t)',
             f'\t\t\t(property "Datasheet" "{datasheet}"\n\t\t\t\t(at 0 0 0)\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t)\n\t\t\t\t\t(hide yes)\n\t\t\t\t)\n\t\t\t)',
             f'\t\t\t(property "Description" "{description}"\n\t\t\t\t(at 0 0 0)\n\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t)\n\t\t\t\t\t(hide yes)\n\t\t\t\t)\n\t\t\t)',
             f'\t\t\t(symbol "{name}_0_1"',
             f"\t\t\t\t(rectangle\n\t\t\t\t\t(start {-width/2} {height/2})\n\t\t\t\t\t(end {width/2} {-height/2})\n\t\t\t\t\t(stroke\n\t\t\t\t\t\t(width 0.254)\n\t\t\t\t\t\t(type default)\n\t\t\t\t\t)\n\t\t\t\t\t(fill\n\t\t\t\t\t\t(type background)\n\t\t\t\t\t)\n\t\t\t\t)",
             "\t\t\t)",
             f'\t\t\t(symbol "{name}_1_1"']
    pin_pos = {}
    for idx, (num, nm) in enumerate(left):
        y = top - idx * pitch
        x = -width / 2 - pin_len
        lines.append(f'\t\t\t\t(pin passive line\n\t\t\t\t\t(at {x} {y} 0)\n\t\t\t\t\t(length {pin_len})\n\t\t\t\t\t(name "{nm}"\n\t\t\t\t\t\t(effects\n\t\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t\t)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t\t(number "{num}"\n\t\t\t\t\t\t(effects\n\t\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t\t)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)')
        pin_pos[num] = (x, y)
    for idx, (num, nm) in enumerate(right):
        y = top - idx * pitch
        x = width / 2 + pin_len
        lines.append(f'\t\t\t\t(pin passive line\n\t\t\t\t\t(at {x} {y} 180)\n\t\t\t\t\t(length {pin_len})\n\t\t\t\t\t(name "{nm}"\n\t\t\t\t\t\t(effects\n\t\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t\t)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t\t(number "{num}"\n\t\t\t\t\t\t(effects\n\t\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t\t)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)')
        pin_pos[num] = (x, y)
    for (num, nm) in pad_pins:
        x, y = 0.0, -height / 2 - pin_len
        lines.append(f'\t\t\t\t(pin passive line\n\t\t\t\t\t(at {x} {y} 90)\n\t\t\t\t\t(length {pin_len})\n\t\t\t\t\t(name "{nm}"\n\t\t\t\t\t\t(effects\n\t\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t\t)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t\t(number "{num}"\n\t\t\t\t\t\t(effects\n\t\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t\t)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)')
        pin_pos[num] = (x, y)
    lines += ["\t\t\t)", "\t\t\t(embedded_fonts no)", "\t\t)"]
    return "\n".join(lines), pin_pos


# ---------------------------------------------------------------- schematic writer
class Project:
    def __init__(self, name: str, title: str, paper: str = "A2"):
        self.name = name
        self.title = title
        self.paper = paper
        self.root = uid()
        self.symbols: dict[str, str] = {}      # lib_id -> embedded block
        self.pin_cache: dict[str, list] = {}   # lib_id -> pins
        self.custom: dict[str, tuple] = {}     # lib_id -> (block, pin_pos)
        self.instances: list[str] = []
        self.wires: list[str] = []
        self.labels: list[str] = []
        self.noconn: list[str] = []
        self.placed = 0

    def _register(self, lib_id: str):
        if lib_id in self.symbols:
            return
        if lib_id in self.custom:
            block, _ = self.custom[lib_id]
            self.symbols[lib_id] = block
            return
        lib, nm = lib_id.split(":")
        block = lib_symbol_block(lib, nm)
        self.symbols[lib_id] = block
        self.pin_cache[lib_id] = symbol_pins(block)

    def add_custom(self, lib_id, value, pins, footprint, datasheet, description):
        block, pin_pos = make_ic_symbol(lib_id, value, pins, footprint, datasheet, description)
        self.custom[lib_id] = (block, pin_pos)
        CUSTOM_LIB[lib_id] = block
        self.symbols.pop(lib_id, None)
        self._register(lib_id)

    def place(self, ref: str, value: str, lib_id: str, footprint: str, X: float, Y: float,
              nets: dict[str, str | None], datasheet: str = "~"):
        X = round(X / 2.54) * 2.54
        Y = round(Y / 2.54) * 2.54
        self._register(lib_id)
        if lib_id in self.custom:
            order = list(self.custom[lib_id][1].keys())
            geom = [(n, self.custom[lib_id][1][n][0], self.custom[lib_id][1][n][1]) for n in order]
        else:
            geom = [(t[0], t[2], t[3]) for t in self.pin_cache[lib_id]]
        pins = geom

        L = ["\t(symbol", f'\t\t(lib_id "{lib_id}")', f"\t\t(at {X} {Y} 0)", "\t\t(unit 1)",
             "\t\t(exclude_from_sim no)", "\t\t(in_bom yes)", "\t\t(on_board yes)", "\t\t(dnp no)",
             f'\t\t(uuid "{uid()}")']
        props = [("Reference", ref, -1), ("Value", value, 0), ("Footprint", footprint, 1),
                 ("Datasheet", datasheet, 2), ("Description", "", 3)]
        for prop, val, k in props:
            hide = "\n\t\t\t\t(hide yes)" if prop in ("Footprint", "Datasheet", "Description") else ""
            L += [f'\t\t(property "{prop}" "{val}"',
                  f"\t\t\t(at {round(X,4)} {round(Y - 3.81 - k*2.54,4)} 0)",
                  "\t\t\t(effects", "\t\t\t\t(font", "\t\t\t\t\t(size 1.27 1.27)", "\t\t\t\t)" + hide, "\t\t\t)", "\t\t)"]
        for (num, *rest) in pins:
            L += [f'\t\t(pin "{num}"', f'\t\t\t(uuid "{uid()}")', "\t\t)"]
        L += ["\t\t(instances", f'\t\t\t(project "{self.name}"', f'\t\t\t\t(path "/{self.root}"',
              f'\t\t\t\t\t(reference "{ref}")', "\t\t\t\t\t(unit 1)", "\t\t\t\t)", "\t\t\t)", "\t\t)", "\t)"]
        self.instances.append("\n".join(L))

        # per-pin wire + label / no_connect
        for (num, px, py) in pins:
            ex, ey = X + px, Y - py
            net = nets.get(str(num), "__NONE__")
            if net is None:
                self.noconn.append(f'\t(no_connect\n\t\t(at {round(ex,4)} {round(ey,4)})\n\t\t(uuid "{uid()}")\n\t)')
                continue
            if net == "__NONE__":
                continue
            ox, oy = ex - X, ey - Y
            n = (ox * ox + oy * oy) ** 0.5 or 1.0
            ox, oy = ox / n, oy / n
            tx, ty = round(ex + ox * 3.81, 4), round(ey + oy * 3.81, 4)
            self.wires.append(f'\t(wire\n\t\t(pts\n\t\t\t(xy {round(ex,4)} {round(ey,4)}) (xy {tx} {ty})\n\t\t)\n\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{uid()}")\n\t)')
            self.labels.append(
                f'\t(global_label "{net}"\n\t\t(shape input)\n\t\t(at {tx} {ty} 0)\n\t\t(fields_autoplaced yes)\n'
                f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify left)\n\t\t)\n'
                f'\t\t(uuid "{uid()}")\n\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}"\n'
                f'\t\t\t(at {tx} {ty} 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)\n\t)')

    def write(self, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        body = ["(kicad_sch", "\t(version 20250114)", '\t(generator "eeschema")', '\t(generator_version "9.0")',
                f'\t(uuid "{self.root}")', f'\t(paper "{self.paper}")',
                "\t(title_block", f'\t\t(title "{self.title}")', '\t\t(rev "1")', "\t\t(company \"Engineering Prototype Design — Not Hardware Validated\")", "\t)",
                "\t(lib_symbols"]
        for lib_id in sorted(self.symbols):
            body.append(self.symbols[lib_id])
        body.append("\t)")
        body += self.wires + self.labels + self.noconn + self.instances
        body += ["\t(sheet_instances", '\t\t(path "/"', '\t\t\t(page "1")', "\t\t)", "\t)", "\t(embedded_fonts no)", ")"]
        sch = out_dir / f"{self.name}.kicad_sch"
        sch.write_text("\n".join(body) + "\n", encoding="utf-8")
        (out_dir / f"{self.name}.kicad_pro").write_text(
            json.dumps({"board": {"design_settings": {"defaults": {}, "diff_pair_dimensions": [], "drc_exclusions": [], "rules": {}, "track_widths": [], "via_dimensions": []}},
                        "boards": [], "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
                        "meta": {"filename": f"{self.name}.kicad_pro", "version": 1},
                        "net_settings": {"classes": [], "meta": {"version": 0}},
                        "pcbnew": {"page_layout_descr_file": ""}, "sheets": [], "text_variables": {}}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return sch


def write_lib_tables(out_dir: Path, sym_libs: list[str], fp_libs: list[str]):
    sym = ["(sym_lib_table", "\t(version 7)"]
    for lib in sym_libs:
        if lib == "BatteryLab":
            sym.append('\t(lib (name "BatteryLab")(type "KiCad")(uri "${KIPRJMOD}/../libraries/BatteryLab.kicad_sym")(options "")(descr "BatteryLab custom symbols"))')
        else:
            sym.append(f'\t(lib (name "{lib}")(type "KiCad")(uri "${{KICAD10_SYMBOL_DIR}}/{lib}.kicad_sym")(options "")(descr ""))')
    sym.append(")")
    (out_dir / "sym-lib-table").write_text("\n".join(sym) + "\n", encoding="utf-8")
    fp = ["(fp_lib_table", "\t(version 7)"]
    for lib in fp_libs:
        fp.append(f'\t(lib (name "{lib}")(type "KiCad")(uri "${{KICAD10_FOOTPRINT_DIR}}/{lib}.pretty")(options "")(descr ""))')
    fp.append(")")
    (out_dir / "fp-lib-table").write_text("\n".join(fp) + "\n", encoding="utf-8")


def read_pins(csv_path: Path) -> list[tuple[str, str]]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [(r["pin_number"], r["pin_name"]) for r in rows]


def read_expected_nets(csv_path: Path) -> dict[str, str | None]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        rule = r["connection_rule"].strip()
        out[r["pin_number"]] = None if rule == "ALLOWED_UNCONNECTED" else r["expected_net"].strip()
    return out


# ---------------------------------------------------------------- BMS build
def build_bms(version: str = "V2"):
    p = Project(f"BatteryLab_BMS_{version}", "BatteryLab 3S BMS (BQ76922) — Engineering Draft")
    bq_pins = read_pins(REQ / "bms_pin_mapping.csv")
    nets = read_expected_nets(REQ / "bms_pin_mapping.csv")
    p.add_custom("BatteryLab:BQ76922", "BQ76922", bq_pins,
                 "Package_DFN_QFN:Texas_RSN_WQFN-32-1EP_4x4mm_P0.4mm_EP2.8x2.8mm",
                 "https://www.ti.com/lit/ds/symlink/bq76922.pdf",
                 "3S-5S Battery Monitor / Protector, RSN 32-pin WQFN")
    # NMOS SON 5x6 custom symbol matching Texas_S-PVSON-N8 pads 1-9
    nmos_pins = [("1", "S"), ("2", "S"), ("3", "S"), ("4", "G"), ("5", "D"), ("6", "D"), ("7", "D"), ("8", "D"), ("9", "D")]
    p.add_custom("BatteryLab:NMOS_SON5x6", "NMOS", nmos_pins,
                 "Package_SON:Texas_S-PVSON-N8", "~", "N-channel MOSFET, SON 5x6 (pinout assumed; verify datasheet)")

    R = "Device:R"
    C = "Device:C"

    # U1 at top-left
    p.place("U1", "BQ76922", "BatteryLab:BQ76922",
            "Package_DFN_QFN:Texas_RSN_WQFN-32-1EP_4x4mm_P0.4mm_EP2.8x2.8mm",
            80, 120, nets, "https://www.ti.com/lit/ds/symlink/bq76922.pdf")

    # MOSFET back-to-back
    p.place("Q1", "CSD18540Q5B", "BatteryLab:NMOS_SON5x6", "Package_SON:Texas_S-PVSON-N8",
            200, 60, {"1": "MID_NODE", "2": "MID_NODE", "3": "MID_NODE", "4": "DSG_GATE",
                      "5": "BAT_POS", "6": "BAT_POS", "7": "BAT_POS", "8": "BAT_POS", "9": "BAT_POS"})
    p.place("Q2", "CSD18540Q5B", "BatteryLab:NMOS_SON5x6", "Package_SON:Texas_S-PVSON-N8",
            200, 120, {"1": "PACK_POS", "2": "PACK_POS", "3": "PACK_POS", "4": "CHG_GATE",
                       "5": "MID_NODE", "6": "MID_NODE", "7": "MID_NODE", "8": "MID_NODE", "9": "MID_NODE"})

    # shunt
    p.place("RS1", "0.01R", R, "Resistor_SMD:R_2010_5025Metric", 260, 60, {"1": "GND", "2": "PACK_NEG"})

    # cell filter resistors
    p.place("R101", "47R", R, "Resistor_SMD:R_1206_3216Metric", 260, 100, {"1": "GND", "2": "CELL_0_NEG"})
    p.place("R102", "47R", R, "Resistor_SMD:R_1206_3216Metric", 260, 120, {"1": "C0P", "2": "CELL_0_POS"})
    p.place("R103", "47R", R, "Resistor_SMD:R_1206_3216Metric", 260, 140, {"1": "C1P", "2": "CELL_1_POS"})
    p.place("R104", "47R", R, "Resistor_SMD:R_1206_3216Metric", 260, 160, {"1": "C1P", "2": "CELL_2_NEG"})
    p.place("R105", "47R", R, "Resistor_SMD:R_1206_3216Metric", 260, 180, {"1": "BAT_POS", "2": "CELL_2_POS"})
    p.place("R106", "0R", R, "Resistor_SMD:R_0603_1608Metric", 300, 100, {"1": "CELL_1_POS", "2": "CELL_1_POS"})
    p.place("R107", "0R", R, "Resistor_SMD:R_0603_1608Metric", 300, 120, {"1": "CELL_0_NEG", "2": "GND"})

    # cell differential caps
    p.place("C101", "0.22uF", C, "Capacitor_SMD:C_0402_1005Metric", 300, 140, {"1": "CELL_0_NEG", "2": "CELL_0_POS"})
    p.place("C102", "0.22uF", C, "Capacitor_SMD:C_0402_1005Metric", 300, 160, {"1": "CELL_0_POS", "2": "CELL_1_POS"})
    p.place("C103", "0.22uF", C, "Capacitor_SMD:C_0402_1005Metric", 300, 180, {"1": "CELL_2_NEG", "2": "CELL_2_POS"})
    p.place("C104", "2.2uF", C, "Capacitor_SMD:C_0603_1608Metric", 340, 100, {"1": "REG18", "2": "GND"})
    p.place("C105", "2.2uF", C, "Capacitor_SMD:C_0603_1608Metric", 340, 120, {"1": "REG1_3V3", "2": "GND"})

    # bias / pullups / NTC / sense filters
    p.place("R108", "100R", R, "Resistor_SMD:R_0603_1608Metric", 340, 140, {"1": "BAT_POS", "2": "BAT_AFE"})
    p.place("R109", "2.2k", R, "Resistor_SMD:R_0603_1608Metric", 340, 160, {"1": "REG1_3V3", "2": "I2C_SCL"})
    p.place("R110", "2.2k", R, "Resistor_SMD:R_0603_1608Metric", 340, 180, {"1": "REG1_3V3", "2": "I2C_SDA"})
    p.place("R112", "10k", R, "Resistor_SMD:R_0603_1608Metric", 380, 100, {"1": "REG18", "2": "NTC_INPUT"})
    p.place("R113", "100R", R, "Resistor_SMD:R_0603_1608Metric", 380, 120, {"1": "GND", "2": "SENSE_P"})
    p.place("R114", "100R", R, "Resistor_SMD:R_0603_1608Metric", 380, 140, {"1": "PACK_NEG", "2": "SENSE_N"})

    # connectors
    p.place("J1", "3S CELL", "Connector_Generic:Conn_01x04", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
            420, 60, {"1": "GND", "2": "C0P", "3": "C1P", "4": "BAT_POS"})
    p.place("J2", "PACK", "Connector_Generic:Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            420, 100, {"1": "PACK_POS", "2": "PACK_NEG"})
    p.place("J3", "I2C", "Connector_Generic:Conn_01x04", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
            420, 140, {"1": "GND", "2": "REG1_3V3", "3": "I2C_SCL", "4": "I2C_SDA"})
    p.place("J4", "NTC", "Connector_Generic:Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            420, 180, {"1": "NTC_INPUT", "2": "GND"})

    # test points
    p.place("TP1", "SENSE_P", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", 460, 60, {"1": "SENSE_P"})
    p.place("TP2", "SENSE_N", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", 460, 80, {"1": "SENSE_N"})
    p.place("TP3", "REG1_3V3", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", 460, 100, {"1": "REG1_3V3"})
    p.place("TP4", "CP1_NODE", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", 460, 120, {"1": "CP1_NODE"})

    out = EDA / f"BatteryLab_BMS_{version}"
    sch = p.write(out)
    write_lib_tables(out, ["Device", "Connector_Generic", "Connector", "BatteryLab"],
                     ["Package_DFN_QFN", "Package_SON", "Resistor_SMD", "Capacitor_SMD",
                      "Connector_PinHeader_2.54mm", "TestPoint"])
    return sch


# ---------------------------------------------------------------- Charger build
def build_charger(version: str = "V2"):
    p = Project(f"BatteryLab_Charger_{version}", "BatteryLab 3S Charger (BQ24610) — Engineering Draft")
    bq_pins = read_pins(REQ / "charger_pin_mapping.csv")
    nets = read_expected_nets(REQ / "charger_pin_mapping.csv")
    p.add_custom("BatteryLab:BQ24610", "BQ24610", bq_pins,
                 "Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm",
                 "https://www.ti.com/lit/ds/symlink/bq24610.pdf",
                 "Synchronous Buck Battery Charger Controller, RGE 24-pin VQFN")
    nmos_pins = [("1", "S"), ("2", "S"), ("3", "S"), ("4", "G"), ("5", "D"), ("6", "D"), ("7", "D"), ("8", "D"), ("9", "D")]
    p.add_custom("BatteryLab:NMOS_SON5x6", "NMOS", nmos_pins,
                 "Package_SON:Texas_S-PVSON-N8", "~", "N-channel MOSFET, SON 5x6 (pinout assumed; verify datasheet)")

    R = "Device:R"
    C = "Device:C"

    p.place("U2", "BQ24610", "BatteryLab:BQ24610",
            "Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm",
            80, 120, nets, "https://www.ti.com/lit/ds/symlink/bq24610.pdf")

    p.place("Q3", "CSD17578Q5A", "BatteryLab:NMOS_SON5x6", "Package_SON:Texas_S-PVSON-N8",
            200, 60, {"1": "PHASE", "2": "PHASE", "3": "PHASE", "4": "HIDRV_GATE",
                      "5": "ADAPTER_P", "6": "ADAPTER_P", "7": "ADAPTER_P", "8": "ADAPTER_P", "9": "ADAPTER_P"})
    p.place("Q4", "CSD17581Q5A", "BatteryLab:NMOS_SON5x6", "Package_SON:Texas_S-PVSON-N8",
            200, 120, {"1": "GND", "2": "GND", "3": "GND", "4": "LODRV_GATE",
                       "5": "PHASE", "6": "PHASE", "7": "PHASE", "8": "PHASE", "9": "PHASE"})
    p.place("L1", "22uH", "Device:L", "Inductor_SMD:L_Bourns_SRN6045TA", 260, 60, {"1": "PHASE", "2": "SENSE_P"})
    p.place("RS2", "0.01R", R, "Resistor_SMD:R_2010_5025Metric", 260, 100, {"1": "SENSE_P", "2": "SENSE_N"})
    p.place("RS3", "0.01R", R, "Resistor_SMD:R_2010_5025Metric", 260, 120, {"1": "INPUT_RAW", "2": "ADAPTER_P"})

    p.place("R201", "100k", R, "Resistor_SMD:R_0603_1608Metric", 300, 60, {"1": "VFB", "2": "GND"})
    p.place("R202", "475k", R, "Resistor_SMD:R_0603_1608Metric", 300, 80, {"1": "SENSE_N", "2": "VFB"})
    p.place("R203", "154k", R, "Resistor_SMD:R_0603_1608Metric", 300, 100, {"1": "VREF_3V3", "2": "ISET1"})
    p.place("R204", "10k", R, "Resistor_SMD:R_0603_1608Metric", 300, 120, {"1": "ISET1", "2": "GND"})
    p.place("R205", "316k", R, "Resistor_SMD:R_0603_1608Metric", 300, 140, {"1": "VREF_3V3", "2": "ISET2"})
    p.place("R206", "10k", R, "Resistor_SMD:R_0603_1608Metric", 300, 160, {"1": "ISET2", "2": "GND"})
    p.place("R207", "100k", R, "Resistor_SMD:R_0603_1608Metric", 340, 60, {"1": "VREF_3V3", "2": "ACSET"})
    p.place("R208", "10k", R, "Resistor_SMD:R_0603_1608Metric", 340, 80, {"1": "ACSET", "2": "GND"})
    p.place("R209", "430k", R, "Resistor_SMD:R_0603_1608Metric", 340, 100, {"1": "VREF_3V3", "2": "TS_NTC"})
    p.place("R210", "9.31k", R, "Resistor_SMD:R_0603_1608Metric", 340, 120, {"1": "TS_NTC", "2": "GND"})

    p.place("C201", "56nF", C, "Capacitor_SMD:C_0603_1608Metric", 340, 140, {"1": "TTC", "2": "GND"})
    p.place("C202", "1uF", C, "Capacitor_SMD:C_0603_1608Metric", 340, 160, {"1": "VREF_3V3", "2": "GND"})
    p.place("C203", "1uF", C, "Capacitor_SMD:C_0603_1608Metric", 340, 180, {"1": "REGN", "2": "GND"})
    p.place("C204", "0.1uF", C, "Capacitor_SMD:C_0402_1005Metric", 380, 60, {"1": "BTST", "2": "PHASE"})
    p.place("C205", "4.7uF", C, "Capacitor_SMD:C_1206_3216Metric", 380, 80, {"1": "SENSE_P", "2": "GND"})
    p.place("C206", "4.7uF", C, "Capacitor_SMD:C_1206_3216Metric", 380, 100, {"1": "SENSE_P", "2": "GND"})
    p.place("C207", "10uF", C, "Capacitor_SMD:C_1206_3216Metric", 380, 120, {"1": "ADAPTER_P", "2": "GND"})

    p.place("D1", "BAT54", "Device:D_Schottky", "Diode_SMD:D_SOD-323", 380, 140, {"1": "REGN", "2": "BTST"})

    p.place("J5", "ADAPTER", "Connector_Generic:Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            420, 60, {"1": "INPUT_RAW", "2": "ADAPTER_N"})
    p.place("J6", "BATTERY", "Connector_Generic:Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            420, 100, {"1": "SENSE_N", "2": "GND"})

    p.place("TP5", "ADAPTER_P", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", 460, 60, {"1": "ADAPTER_P"})
    p.place("TP6", "PHASE", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", 460, 80, {"1": "PHASE"})
    p.place("TP7", "SENSE_P", "Connector:TestPoint", "TestPoint:TestPoint_Pad_1.5x1.5mm", 460, 100, {"1": "SENSE_P"})

    out = EDA / f"BatteryLab_Charger_{version}"
    sch = p.write(out)
    write_lib_tables(out, ["Device", "Connector_Generic", "Connector", "BatteryLab"],
                     ["Package_DFN_QFN", "Package_SON", "Resistor_SMD", "Capacitor_SMD",
                      "Inductor_SMD", "Diode_SMD", "Connector_PinHeader_2.54mm", "TestPoint"])
    return sch


def write_battery_lab_lib() -> Path:
    libs = EDA / "libraries"
    libs.mkdir(parents=True, exist_ok=True)
    lines = ["(kicad_symbol_lib", "\t(version 20251024)", '\t(generator "kicad_symbol_editor")', '\t(generator_version "10.0")']
    for lib_id in sorted(CUSTOM_LIB):
        block = CUSTOM_LIB[lib_id]
        short = lib_id.split(":", 1)[1]
        block = block.replace(f'(symbol "{lib_id}"', f'(symbol "{short}"', 1)
        # 原生 .kicad_sym 的符号块不包含 embedded_fonts（该标记只在 .kicad_sch 内嵌时使用）
        block = block.replace("\n\t\t\t(embedded_fonts no)", "")
        lines.append(block)
    lines += ["\t(embedded_fonts no)", ")"]
    path = libs / "BatteryLab.kicad_sym"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    version = "V2"
    for arg in sys.argv[1:]:
        if arg.startswith("--version="):
            version = arg.split("=", 1)[1]
    bms = build_bms(version)
    chg = build_charger(version)
    lib = write_battery_lab_lib()
    print(json.dumps({"bms": str(bms), "charger": str(chg), "library": str(lib)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

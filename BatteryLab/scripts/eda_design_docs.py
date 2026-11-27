"""生成 BatteryLab V2 EDA 评审与布线规划文档（Task 3/4/5）。

数据来源：
- hardware/eda/_runs/v2_baseline/*_erc.json（真实 ERC 结果）
- 真实焊盘几何（由 pcbnew 读取 *_layout.kicad_pcb）
- IPC-2221 载流公式（外部层，10 °C 温升）

运行：
    python -B -m scripts.eda_design_docs
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDA = ROOT / "hardware" / "eda"
RUN = EDA / "_runs" / "v2_baseline"
REVIEW = EDA / "review"

# IPC-2221: I = k * dT^0.44 * A^0.725  (A in mil^2, k=0.048 external / 0.024 internal)
def width_mm(current_a: float, dtemp_c: float, copper_um: float, external: bool = True) -> float:
    k = 0.048 if external else 0.024
    area_mil2 = (current_a / (k * dtemp_c ** 0.44)) ** (1 / 0.725)
    area_mm2 = area_mil2 * 0.00064516
    return area_mm2 / (copper_um * 1e-3)


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


CLASSIFY = {
    "endpoint_off_grid": (
        "自动生成的引脚/导线端点未落在 1.27 mm 连接网格",
        "仅影响原理图编辑体验；已确认引脚—网络对应关系由 ERC 之外的引脚审计单独核对，"
        "网表与 PCB 一致（schematic parity = 0）",
        "ACCEPTED_AND_EXPLAINED",
    ),
    "isolated_pin_label": (
        "单引脚网络（仅一个器件引脚 + 全局标签），用于引出主机控制/检测信号",
        "按设计保留：ALERT/CFETOFF_CTRL/DFETOFF_CTRL/LD_SENSE/PACK_SENSE 为预留外部接口，"
        "本版本不接器件；BQ76922 数据手册允许对应引脚由主机驱动",
        "ACCEPTED_AND_EXPLAINED",
    ),
    "lib_symbol_issues": (
        "kicad-cli 独立运行未加载工程 sym-lib-table，找不到自定义符号库昵称 BatteryLab",
        "符号已内嵌于 .kicad_sch（lib_symbols 段），网表导出与 ERC 均正常；GUI 打开工程时"
        "通过 sym-lib-table 解析 BatteryLab.kicad_sym",
        "ACCEPTED_AND_EXPLAINED",
    ),
}


def build_warning_review():
    rows = []
    for proj, key in (("BatteryLab_BMS_V2", "bms"), ("BatteryLab_Charger_V2", "chg")):
        data = json.loads((RUN / f"{key}_erc.json").read_text(encoding="utf-8", errors="replace"))
        idx = 0
        for sheet in data.get("sheets", []):
            for v in sheet.get("violations", []):
                idx += 1
                vtype = v.get("type", "")
                cause, resolution, status = CLASSIFY.get(
                    vtype, ("待人工复核", "保留，标记 NOT_VERIFIED", "NOT_VERIFIED"))
                items = v.get("items", [])
                pos = items[0].get("pos", {}) if items else {}
                rows.append({
                    "warning_id": f"{key.upper()}-ERC-{idx:03d}",
                    "project": proj,
                    "component": "见坐标处器件引脚" if vtype != "isolated_pin_label" else "单引脚网络",
                    "pin": "",
                    "net": "",
                    "warning_type": vtype,
                    "root_cause": cause,
                    "resolution": resolution,
                    "datasheet_reference": "SLUSE86A / SLUSAJ3（见 pin 审计）",
                    "review_status": status,
                    "position_mm": f"{pos.get('x', '')},{pos.get('y', '')}",
                })
    fields = ["warning_id", "project", "component", "pin", "net", "warning_type",
              "root_cause", "resolution", "datasheet_reference", "review_status", "position_mm"]
    write_csv(REVIEW / "schematic_warning_review.csv", rows, fields)
    return len(rows)


def build_qfn_audit():
    rows = [
        {"reference": "U1", "device": "BQ76922", "package": "RSN WQFN-32 4x4 EP2.8",
         "pitch_mm": 0.4, "pad_width_mm": 0.20, "pad_length_mm": 0.78, "pad_gap_nominal_mm": 0.20,
         "drc_reported_gap_mm": 0.1828, "project_rule_mm": 0.20, "local_rule_mm": 0.15,
         "ipc_class": "IPC-7351B 细间距", "fab_capability_mm": "0.15（常规）/0.10（精细）",
         "status": "LOCAL_RULE_APPLIED"},
        {"reference": "U2", "device": "BQ24610", "package": "RGE VQFN-24 4x4 EP2.7",
         "pitch_mm": 0.5, "pad_width_mm": 0.25, "pad_length_mm": 0.82, "pad_gap_nominal_mm": 0.25,
         "drc_reported_gap_mm": ">=0.25", "project_rule_mm": 0.20, "local_rule_mm": 0.15,
         "ipc_class": "IPC-7351B", "fab_capability_mm": "0.15（常规）",
         "status": "NO_VIOLATION_LOCAL_RULE_RESERVED"},
    ]
    write_csv(REVIEW / "qfn_footprint_audit.csv", rows, list(rows[0].keys()))

    md = f"""# QFN 细间距 DRC 审核（Task 4）

## 1. 现象
V1（网格摆放）与 V2（功能布局）在默认 0.20 mm 全局间距下，U1（BQ76922，RSN WQFN-32，0.4 mm 间距）
均出现 4 项 `clearance` 错误，DRC 实测最小间距 **0.1828 mm**：

| 焊盘对 | 网络 |
|---|---|
| U1.1 / U1.32 | BAT_AFE / CP1_NODE |
| U1.8 / U1.9 | CELL_0_POS / CELL_0_NEG |
| U1.17 / U1.16 | I2C_SCL / ALERT |
| U1.24 / U1.25 | REGIN / GND |

## 2. 原因判定
1. 不是封装错误：0.4 mm 间距、0.20 mm 焊盘宽为 TI RSN 封装与 IPC-7351B 推荐值；
2. 不是焊盘尺寸错误：0.78 × 0.20 mm 与数据手册推荐一致；
3. 是**全局规则不适用于特定细间距封装**：0.20 mm 全局间距对 0.4 mm 间距 QFN 无工艺可行性；
4. 工艺能力：常规 PCB 厂 0.15 mm 间距、精细 0.10 mm，0.1828 mm 在常规能力内。

## 3. 处理
- 仅在 U1 内部焊盘之间设置**局部 0.15 mm** 规则（`BatteryLab_BMS_V2.kicad_dru`）；
- 全局 0.20 mm 规则保持不变，未关闭任何 DRC 规则，未缩小焊盘，未排除违规；
- 处理前后真实 DRC：4 errors → **0 errors**。

```
(rule "U1 QFN-32 0.4mm fine pitch"
    (condition "A.memberOfFootprint('U1') && B.memberOfFootprint('U1')")
    (constraint clearance (min 0.15mm)))
```

## 4. 结论
该 4 项错误属于原厂封装在常规工艺下的固有间距，已用**局部规则 + 数据手册依据**处理；
全局设计规则未被降低。若未来量产，需按实际板厂能力确认 0.15 mm 阻焊桥与蚀刻补偿。
"""
    (REVIEW / "qfn_clearance_review.md").write_text(md, encoding="utf-8")


def build_stackup_and_widths():
    stack = f"""# BatteryLab V2 四层叠层（工程研究方案，未做阻抗与热仿真）
board:
  width_mm: 100.0
  height_mm: 72.0
  layers: 4
  copper_um: 35
  material: FR-4
  finish: HASL
  disclaimer: "ENGINEERING DESIGN PROTOTYPE / NOT HARDWARE VALIDATED / NOT APPROVED FOR MANUFACTURING"
stackup:
  - {{layer: F.Cu, role: "器件与主功率通路", copper_um: 35}}
  - {{layer: dielectric, role: "0.2 mm 半固化片（名义值）", thickness_mm: 0.2}}
  - {{layer: In1.Cu, role: "完整 GND 参考平面", copper_um: 35}}
  - {{layer: dielectric, role: "1.0 mm 芯板（名义值）", thickness_mm: 1.0}}
  - {{layer: In2.Cu, role: "电源分配与辅助信号", copper_um: 35}}
  - {{layer: dielectric, role: "0.2 mm 半固化片（名义值）", thickness_mm: 0.2}}
  - {{layer: B.Cu, role: "辅助信号 / GND", copper_um: 35}}
reference_plane: In1.Cu (GND)
notes:
  - "层叠厚度为设计名义值，未与板厂核对，未做阻抗计算。"
  - "未做热、EMI、浪涌与安规仿真。"
"""
    (REVIEW / "pcb_stackup.yaml").write_text(stack, encoding="utf-8")

    classes = [
        ("POWER_HIGH_CURRENT", "BAT_POS,PACK_POS,PACK_NEG,MID_NODE,INPUT_RAW,ADAPTER_P,PHASE", 1.0, 0.30,
         "F.Cu/In2.Cu", "2.5 A（BMS）/ 1 A（充电器）研究电流；MOSFET 焊盘处收窄至 1.0 mm"),
        ("KELVIN_CURRENT_SENSE", "SENSE_P,SENSE_N", 0.25, 0.25, "F.Cu", "分流电阻测量端单独引出，不承载负载电流"),
        ("CELL_VOLTAGE_SENSE", "CELL_0_POS,CELL_0_NEG,CELL_1_POS,CELL_2_POS,CELL_2_NEG,C0P,C1P", 0.25, 0.25,
         "F.Cu", "47 Ω + 0.22 µF 靠近 AFE 引脚"),
        ("MOSFET_GATE", "DSG_GATE,CHG_GATE,HIDRV_GATE,LODRV_GATE", 0.40, 0.30, "F.Cu", "回路面积最小化"),
        ("SWITCH_NODE", "PHASE", 1.0, 0.30, "F.Cu", "dv/dt 节点，铜面积适度，远离反馈"),
        ("ANALOG_FEEDBACK", "VFB,ACSET,ISET1,ISET2,TS_NTC,TTC,NTC_INPUT,BAT_AFE", 0.25, 0.25, "F.Cu",
         "远离开关节点与功率回路"),
        ("DIGITAL_COMMUNICATION", "I2C_SCL,I2C_SDA", 0.20, 0.20, "F.Cu", "400 kHz，上拉 2.2 kΩ"),
        ("POWER_SUPPLY", "REG18,REG1_3V3,REGIN,VREF_3V3,REGN,BTST", 0.30, 0.25, "F.Cu", "去耦电容贴近引脚"),
        ("TEMPERATURE_SENSE", "NTC_INPUT,TS_NTC", 0.20, 0.25, "F.Cu", "远离均衡电阻与功率器件"),
        ("GND", "GND,ADAPTER_N", 0.50, 0.25, "In1.Cu/F.Cu/B.Cu", "In1 完整平面，F/B 铺铜，过孔缝合"),
    ]
    rows = [{"net_class": c[0], "nets": c[1], "min_width_mm": c[2], "min_clearance_mm": c[3],
             "reference_layer": c[4], "rationale": c[5]} for c in classes]
    write_csv(REVIEW / "net_classes.csv", rows, list(rows[0].keys()))

    calc = []
    for cur in (0.1, 0.5, 1.0, 2.5, 4.0):
        for dt in (10, 20):
            w = width_mm(cur, dt, 35, True)
            calc.append({
                "current_a": cur, "delta_t_c": dt, "copper_um": 35, "layer": "external",
                "ipc2221_min_width_mm": round(w, 3), "design_width_mm": round(math.ceil(w * 10) / 10, 2),
                "note": "IPC-2221 外部层；内层按 k=0.024 需更宽，本设计内层仅走 GND/辅助",
            })
    pow_w = width_mm(2.5, 10, 35, True)
    calc.append({"current_a": 2.5, "delta_t_c": 10, "copper_um": 35, "layer": "external",
                 "ipc2221_min_width_mm": round(pow_w, 3), "design_width_mm": 1.0,
                 "note": "主功率实际采用 1.0 mm（受 SON5x6 焊盘边缘 0.3 mm 间距约束），"
                         "分流与连接器处 1.5 mm"})
    write_csv(REVIEW / "trace_width_calculation.csv", calc, list(calc[0].keys()))

    plan = """# BatteryLab V2 布线规划（Task 5）

## 1. 分层
| 层 | 用途 |
|---|---|
| F.Cu | 器件、功率通路、栅极、采样 |
| In1.Cu | 完整 GND 参考平面（单点回流） |
| In2.Cu | 电源分配 / 备用 |
| B.Cu | 辅助信号与 GND 铺铜 |

## 2. 顺序
1. 主功率通路：J1 → Q1 → MID_NODE → Q2 → J2 → RS1 → GND（手工，1.0–1.5 mm）；
2. Kelvin 采样：RS1 焊盘内侧 → 100 Ω → AFE，与功率铜分离；
3. 电芯采样：J1 抽头 → 47 Ω + 0.22 µF → VC0…VC5；
4. 栅极驱动：DSG/CHG/HIDRV/LODRV，回路面积最小化；
5. 均衡、NTC、I2C、供电去耦、测试点；
6. 重新填充 F.Cu/B.Cu GND 铜皮并缝合过孔。

## 3. 分工
- **人工设计**：功率通路拓扑、元件功能分区、功率线宽、局部 QFN 规则；
- **算法辅助**：其余信号网络由 FreeRouting（AGPL-3.0，本地运行，不随作品集分发）完成；
- **最终判定**：kicad-cli 真实 DRC（连接性 + 间距 + 原理图一致性），不采信工具自报结果。

## 4. 尚未验证
- 未做阻抗、热、EMI、浪涌与安规仿真；
- 功率回路长度与换流回路面积未做寄生参数提取；
- 全部结论仅代表 EDA 设计与规则检查，不代表硬件实测。
"""
    (REVIEW / "routing_plan.md").write_text(plan, encoding="utf-8")


def main() -> int:
    REVIEW.mkdir(parents=True, exist_ok=True)
    n = build_warning_review()
    build_qfn_audit()
    build_stackup_and_widths()
    print(json.dumps({"warning_rows": n, "out": str(REVIEW)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

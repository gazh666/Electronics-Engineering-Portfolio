# 复现步骤（Reproducibility）

## 环境基线
| 项目 | 环境名 | Python | 关键依赖 |
|---|---|---|---|
| TestLab | `kaifa` | 3.11 | PyVISA-sim、Streamlit、pytest |
| PowerLab | `kaifa_power` | 3.11.18 | PySpice 1.5、ngspice 34 DLL |
| BatteryLab | `kaifa_battery` | 3.11 | NumPy/SciPy/pandas/matplotlib、pytest |
| BatteryLab EDA | KiCad 10.0.8 | — | `kicad-cli` + `pcbnew`（KiCad 自带 Python） |

## 1. 测试
```powershell
conda run -n kaifa python -m pytest TestLab/tests -q
conda run -n kaifa_power python -m pytest PowerLab/tests -q
conda run -n kaifa_battery python -m pytest BatteryLab/tests -q
```

## 2. BatteryLab 仿真
```powershell
conda run -n kaifa_battery python -B -m scripts.run_all_hardening   # 若存在，按项目 README
conda run -n kaifa_battery python -B -m scripts.audit_resume_metrics
```

## 3. BatteryLab EDA（需要 KiCad 10）
```powershell
$pyk = "C:\Users\<you>\AppData\Local\Programs\KiCad\10.0\bin\python.exe"

# 3.1 原理图 -> 网表
kicad-cli sch export netlist --format kicadxml --output netlist.xml BatteryLab_BMS_V2.kicad_sch

# 3.2 布局 + 功率布线
& $pyk scripts\layout_eda_pcb_v2.py netlist.xml board.kicad_pcb BMS
& $pyk scripts\route_power_eda.py board.kicad_pcb BMS

# 3.3 DSN -> 辅助布线 -> SES
& $pyk scripts\export_dsn.py board.kicad_pcb board.dsn 0.18
python -B -m scripts.run_freerouting board.dsn board.ses 10   # 需要本地 FreeRouting 1.9.0

# 3.4 SES 导入 + 重新铺铜
& $pyk scripts\import_ses_refill.py board.kicad_pcb board.ses

# 3.5 真实 ERC / DRC / 引脚审计
& $pyk -B -m scripts.verify_final_pcb BatteryLab_BMS_V2
& $pyk -B -m scripts.verify_final_pcb BatteryLab_Charger_V2

# 3.6 导出制造与审查文件
python -B -m scripts.export_release_v2 BatteryLab_BMS_V2
```

## 4. 已完成的验收（2026-11-27）
- BMS：0 DRC 错误、0 未连接、4 项一致性差异（M3 安装孔）；
- 充电器：0 DRC 错误、0 未连接、4 项一致性差异；
- 两块板：0 ERC 错误；告警 59 / 50 已逐条分类。

## 5. 已知不可自动复现的部分
- PCB 位图（PNG）与 3D 渲染需要 KiCad GUI，CLI 只能导出 SVG / STEP；
- FreeRouting 为第三方工具，需用户自行下载（AGPL-3.0），仓库不提供二进制；
- 真实硬件验证（打样/焊接/电池实验）不在本项目范围内。

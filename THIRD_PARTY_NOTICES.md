# 第三方组件、数据与工具许可说明 (THIRD_PARTY_NOTICES)

本仓库的 `LICENSE`（MIT）**仅覆盖仓库所有者原创及 AI 辅助开发的代码、文档与原创工程文件**。
下列第三方组件、数据、模型、封装与工具**保留各自原始许可证**，不得视为 MIT 授权。

## 1. 是否随仓库分发

| 组件 / 数据 | 用途 | 许可证 | 是否随仓库分发 |
|---|---|---|---|
| Python 3.11 | 运行环境 | PSF-2.0 | 否（环境依赖） |
| PySpice 1.5 | ngspice 的 Python 接口 | **GPL-3.0** | 否（仅 `requirements` 声明） |
| ngspice 34 (64-bit DLL) | SPICE 求解器 | BSD-3-Clause / 部分 GPL | 否（需用户自行安装） |
| PyVISA / PyVISA-sim | SCPI 虚拟仪器 | MIT | 否（仅 `requirements` 声明） |
| Streamlit | TestLab 界面 | Apache-2.0 | 否（仅 `requirements` 声明） |
| NumPy / SciPy / pandas / matplotlib | 计算与绘图 | BSD-3-Clause | 否（仅 `requirements` 声明） |
| pytest / ruff | 测试与静态检查 | MIT | 否（仅 `requirements` 声明） |
| PyBaMM | 电池模型（参考） | BSD-3-Clause | 否（仅 `requirements` 声明） |
| PyYAML / requests / openpyxl / pypdf | 工具依赖 | MIT / Apache-2.0 / BSD | 否（仅 `requirements` 声明） |
| KiCad 10.0.8 | EDA 工具（原理图/PCB/CLI） | **GPL-3.0** | 否（本地安装，未复制） |
| KiCad 官方符号库 / 封装库 | 器件符号与封装 | **CC-BY-SA 4.0** | 部分（见 §3） |
| FreeRouting 1.9.0 | 辅助布线（仅本地使用） | **AGPL-3.0** | **否**（二进制与源码均未上传） |
| CALCE INR18650-20R 公开数据 | 电池模型辨识/验证 | 学术公开数据（见 §5） | 否（仅派生参数与指标） |
| TI BQ76922 / BQ24610 数据手册 | 引脚与外围设计依据 | TI 版权（引用） | 否（仅引用链接与页码） |
| TI CSD18540 / CSD17578 / CSD17581 数据手册 | MOSFET 参数依据 | TI 版权（引用） | 否（仅引用参数） |

## 2. FreeRouting（AGPL-3.0）— 明确排除

- FreeRouting 仅作为**本地辅助布线工具**运行，其程序本体与源码**未进入本仓库**。
- 仓库中的 `.kicad_pcb` 铜箔走线由 FreeRouting 生成的 Specctra `.ses` 导入 KiCad 后得到，
  即 FreeRouting 的输出数据被转换并合并进板文件；FreeRouting 程序本身不随之分发。
- 仓库**不包含** FreeRouting 的 `.jar`、源码、ASCII 工作目录或任何运行日志。
- 后续如需再分发 FreeRouting，须单独遵守 AGPL-3.0。

## 3. KiCad 符号 / 封装库（CC-BY-SA 4.0）

- 仓库中的 `.kicad_pcb` 内嵌了来自 KiCad 官方库的封装图形（来源已在封装属性中标识）。
  这些封装部分按 **CC-BY-SA 4.0** 分发，不适用本仓库的 MIT。
- `BatteryLab/hardware/eda/libraries/BatteryLab.kicad_sym` 为**原创绘制**的符号
  （依据 TI 数据手册引脚表），并非复制 KiCad 官方库文件；其符号图形按本仓库 MIT 授权。
- 若再分发或修改上述封装图形，须保留 CC-BY-SA 4.0 的署名与相同方式共享要求。

## 4. 厂商数据手册与器件参数（TI）

- 仓库**未**附带任何 TI 数据手册 PDF、厂商 SPICE 模型或 IBIS 文件。
- 引脚编号、电压/电流额定值、热阻等参数以**引用**形式出现在引脚映射表与审核文档中，
  并标注数据手册链接与页码；这些事实性数据的版权归 TI 所有。
- MOSFET 行为模型为本人基于数据手册参数建立的简化模型，**不是**厂商内部晶体管级模型。

## 5. CALCE 公开数据使用与分发条件

- 使用 CALCE INR18650-20R SP2 公开数据集进行电池模型参数辨识与验证。
- 仓库**不包含**原始数据文件，仅保存派生的模型参数、拟合指标与重放结果（RMSE 等）。
- CALCE 数据的使用受其原始发布条款约束（学术研究用途）；如需复现，请从 CALCE 官方渠道
  自行获取原始数据，并遵守其使用与引用要求。本仓库不对该数据再做分发或再许可。

## 6. Python 依赖

- 依赖通过各项目 `requirements*.txt` / `requirements-dev.txt` 声明，**不内嵌源码**。
- 其中 PySpice 为 **GPL-3.0**：本仓库以独立进程/库调用方式使用，未与之组合成单一衍生作品；
  若将本项目与 PySpice 一起再分发，需自行评估 GPL-3.0 兼容性。
- 其余依赖多为 MIT / BSD / Apache-2.0，具体以其各自发行包内 LICENSE 为准。

## 7. 不相容 / 无法确认授权的处理

- 任何与 MIT 不兼容（如 GPL/AGPL 程序本体）或授权无法确认的第三方文件，**均未纳入本仓库**，
  或在此单独说明其归属与限制。
- 不得将本仓库全部工程资产统一视为 MIT 授权。

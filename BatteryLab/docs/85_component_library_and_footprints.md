# 85 元件库与封装核对

本文件说明第八阶段如何把官方数据手册的引脚表变成 KiCad 符号与封装，以及为什么本机
无法完成核对。结论先说：**本机没有 KiCad，符号库与封装库均未创建，核对状态全部 BLOCKED。**

## 1. 状态与证据

| 项 | 状态 | 证据 |
| --- | --- | --- |
| KiCad 安装 | 未安装 | PATH 无 `kicad-cli`；`C:\Program Files\KiCad` 不存在 |
| 可安装版本 | winget 提供 KiCad.KiCad 10.0.8 | 仅查询到包，未安装、未提权 |
| 符号库 `.kicad_sym` | 未创建 | 本阶段无任何库文件产物 |
| 封装库 `.kicad_mod` | 未创建 | 同上 |
| 引脚表核对 | 已完成 | BQ76922 33 行、BQ24610 25 行，`verified` 全为 true |
| 焊盘/顶视图核对 | 未完成 | `footprint_verification.csv` 全部 BLOCKED_NO_KICAD |
| BOM | 51 行 | 26 行 BMS + 25 行充电板；critical 10 个全部 VERIFIED_DATASHEET |

## 2. 符号、封装与 3D 模型是三件事

| 层次 | 回答的问题 | 文件/对象 | 本阶段状态 |
| --- | --- | --- | --- |
| 符号 symbol | 逻辑上这是什么器件、引脚叫什么 | `.kicad_sym` 中的 symbol | 未创建 |
| 封装 footprint | 物理上焊盘在哪、多大、几号焊盘 | `.kicad_mod` | 未创建 |
| 3D 模型 | 装到板上有多高、干涉与否 | `.step` / `.wrl` | 未取得 |

三者编号必须对齐：符号的引脚号 1–24 与封装的焊盘号 1–24 一一对应，热焊盘用独立编号
（本阶段约定为 `PAD`）。3D 模型只服务机械评审，不能替代焊盘核对，也不能证明电气连接正确。

常见错误：符号有 24 个引脚、封装有 25 个焊盘却把热焊盘漏连；或符号把两个源极引脚画成
一个，导致网表少一个节点。这类问题 ERC 不一定报错，必须在封装层逐焊盘核对。

## 3. KiCad 库文件结构

| 文件/表 | 作用 | 本阶段是否产生 |
| --- | --- | --- |
| `.kicad_sym` | 符号库，S 表达式文本 | 否 |
| `.kicad_mod` | 单个封装，S 表达式文本 | 否 |
| `sym-lib-table` | 工程/全局符号库索引 | 否 |
| `fp-lib-table` | 工程/全局封装库索引 | 否 |
| `.kicad_sch` | 原理图 | 否（BLOCKED） |
| `.kicad_pcb` | PCB | 否（BLOCKED） |
| `.step` / `.wrl` | 3D 模型，由封装引用路径 | 否 |

`footprint_verification.csv` 里的 `TI_RGE_24_4x4mm`、`TI_RSN_32_4x4mm`、`TI_SON_5x6mm`
是**本项目内部命名**，不是 KiCad 官方库 ID。安装 KiCad 后必须从官方库检索实际封装，
确认焊盘几何后再写回，不能把内部名字当作已验证的官方封装。

## 4. 从官方引脚表生成符号

以 BQ24610 为例，`charger_pin_mapping.csv` 的 25 行（24 引脚 + PAD）直接决定符号：

| 引脚类型（CSV） | KiCad 电气类型 | 例子 |
| --- | --- | --- |
| I（输入） | input | ACN、ACP、CE、TS、TTC、VFB、SRN、SRP、ISET1、ISET2、ACSET、BTST、VCC |
| O（输出） | output | ACDRV、LODRV、HIDRV、BATDRV、VREF、REGN |
| O（开漏状态） | open_collector | STAT1、STAT2、PG |
| P（电源/地） | power_in 或 passive | GND、PAD |
| PH（开关节点） | passive | PH |

生成规则：

1. 引脚号、引脚名逐字照抄数据手册 p.4，不改缩写（ACN 不是 AC_N）。
2. 一个符号单元放全部 24 脚，按功能分组摆放（输入检流、驱动、反馈、状态）。
3. PAD 单独建脚，名称 `PAD`、编号 `PAD` 或约定的 25，类型 passive，必须显式连到 GND。
4. 隐藏引脚一律不用；电源脚必须可见，避免"看不见的隐式连接"。
5. 开漏输出不要设成 output，否则 ERC 可能与外部上拉/别的开漏源报冲突。

BQ76922 同理，33 行 = 32 引脚 + PAD。未用 VC 通道（VC3A/VC3B 短到 VC2）在符号上应
体现为明确的网络连接，而不是留空。

## 5. 封装核对要点

| 检查项 | 为什么必须人工看 | 本阶段状态 |
| --- | --- | --- |
| 焊盘总数 | BQ24610 应 25（24 + EP）；BQ76922 应 33（32 + EP） | BLOCKED |
| 热焊盘 EP | 尺寸、开窗、钢网分割、接地过孔 | BLOCKED |
| 多脚源极 | Son 5×6 的源极占多脚，符号需合并或全部列出 | BLOCKED |
| 1 脚标识 | 顶视图丝印/焊盘形状必须与数据手册一致 | BLOCKED |
| 极性 | 二极管阴极、LED 方向、连接器 1 脚 | BLOCKED |
| 焊盘间距 | 细间距 QFN/VQFN 引脚需确认制造能力 | BLOCKED |
| 阻焊/助焊 | EP 开窗与钢网开孔比例 | BLOCKED |

具体封装预期：

| 器件 | 封装 | 引脚 | 焊盘 | 备注 |
| --- | --- | --- | --- | --- |
| BQ76922 | RSN 32 QFN 4×4 | 32 | 33 | 含热焊盘 |
| BQ24610 | RGE 24 VQFN 4×4 | 24 | 25 | 含热焊盘 |
| CSD18540Q5B / CSD17578Q5A / CSD17581Q5A | Son 5×6 | 8 | 9 | 源极多脚 + 漏极 + 栅极 + 散热焊盘 |
| WSL2010R0100FEA | 2010 | 2 | 2 | 两端子，无极性 |
| SRN6045-220M | 6.0×6.0×4.5 | 2 | 2 | 半屏蔽，无裸露焊盘 |

## 6. 为什么本机 BLOCKED

1. `kicad-cli` 不在 PATH；`C:\Program Files\KiCad` 目录不存在，说明未安装。
2. 本阶段纪律禁止擅自安装系统级软件与请求管理员权限，`scripts/verify_kicad.py` 只检测、
   不安装。
3. 没有 `.kicad_sch` / `.kicad_pcb`，`scripts/audit_schematic.py` 返回
   `BLOCKED_NO_SCHEMATIC`，`scripts/audit_pcb.py` 返回 `BLOCKED_NO_PCB`。
4. `pcbnew` 只随 KiCad 自带 Python 提供；在 `kaifa_battery` 环境中不可用，因此
   `board_metrics` 与 `board_placement` 只能被导入、不能被真正调用。这两个模块把
   `import pcbnew` 放在函数内部，所以 pytest 仍可正常收集。
5. 结果是：引脚表能核对（纯 CSV），焊盘与顶视图不能核对（需要 KiCad 图形界面）。

## 7. 库许可与第三方库核查清单

本阶段**没有**核验任何库的许可条款，因此所有许可结论均为 **NOT_VERIFIED**。使用前逐项确认：

| 核查项 | 要求 |
| --- | --- |
| 库来源 | 只记录官方仓库或可追溯的发布页，不用网盘转载 |
| 许可证 | 抄录许可证名称与版本，确认商用/再分发条件 |
| 归属声明 | 确认原理图/PCB 发布时是否需要署名 |
| 修改条款 | 若改焊盘，确认是否要求以相同许可发布 |
| 文件完整性 | 校验下载包与官方哈希/版本号 |
| 版本冻结 | 记录库版本，避免不同人拉到不同焊盘 |

第三方库额外核查：焊盘是否按数据手册重画、是否包含 EP、是否与官方封装同名但几何不同。
同名不同几何是最危险的情况，必须用数据手册顶视图逐项比对，而不是看名字。

## 8. 用户装好 KiCad 后的核对步骤

以下步骤需要用户自行决定是否安装，并由用户在图形界面完成；本阶段未执行任何一步。

1. 通过官方安装包或 `winget install --id KiCad.KiCad` 安装，勾选符号库、封装库、3D 库。
2. 确认 `C:\Program Files\KiCad\<版本>\bin\kicad-cli.exe version` 可执行。
3. 运行 `python -m scripts.verify_kicad --cli "<路径>\kicad-cli.exe"`，记录真实版本与子命令。
4. 建立工程 `BatteryLab_Charger_V1`，创建 24 + PAD 的 BQ24610 符号。
5. 对照 `charger_pin_mapping.csv` 逐脚核对名称、编号、电气类型。
6. 建立 `BatteryLab_BMS_V1`，创建 32 + PAD 的 BQ76922 符号，核对未用 VC 通道处理。
7. 从官方库选封装，确认焊盘 25/33，EP 尺寸与开窗正确。
8. 核对 Son 5×6 的源极多脚、漏极、栅极与散热焊盘；核对 WSL 2010 与 SRN6045 两端子。
9. 打开 3D 视图检查高度与干涉，但不要用 3D 代替焊盘核对。
10. 导出网表并运行 `python -m scripts.audit_schematic`，确认逐脚 PASS。
11. 把 `footprint_verification.csv` 的 `BLOCKED_NO_KICAD` 改为真实核对结果，保留核对人与日期。
12. 不要从 PyPI 安装同名 `pcbnew`；需要板级指标时使用 KiCad 自带 Python。

## 9. 本文件不能支持的结论

- 不能声称"已创建 KiCad 符号库/封装库"。
- 不能声称"封装已按数据手册核对通过"。
- 不能声称"库许可为某许可证"，本阶段未核验。
- 不能用内部命名 `TI_RGE_24_4x4mm` 冒充官方封装 ID。

## 自测题

**1. 符号、封装、3D 模型分别回答什么问题？**

要点：符号回答逻辑引脚与功能；封装回答焊盘几何与编号；3D 回答机械尺寸与干涉。三者不能互相替代。

**2. BQ24610 的符号应有多少个引脚，PAD 怎么处理？**

要点：24 个功能引脚 + 1 个 PAD（共 25）。PAD 必须是可见引脚并显式接 GND，不能隐藏。

**3. 为什么 `board_metrics` 在无 KiCad 环境仍能被 pytest 导入？**

要点：`import pcbnew` 放在函数内部延迟导入，模块顶层不依赖 pcbnew；真正调用才失败。

**4. 为什么不能把 `TI_RGE_24_4x4mm` 当作已验证封装？**

要点：这是项目内部命名，不是 KiCad 官方库 ID；焊盘几何仍需在 KiCad 中按数据手册核对。

**5. 第三方库最危险的核查点是什么？**

要点：同名不同几何。必须按数据手册顶视图逐一比对焊盘、EP 与 1 脚标识，而不是相信名字。

## 延伸阅读

- KiCad 官方下载页：https://www.kicad.org/download/windows/
- KiCad 官方文档：https://docs.kicad.org/
- KiCad 官方符号库仓库：https://gitlab.com/kicad/libraries/kicad-symbols
- KiCad 官方封装库仓库：https://gitlab.com/kicad/libraries/kicad-footprints
- TI BQ24610 数据手册 SLUS892D：https://www.ti.com/lit/ds/symlink/bq24610.pdf
- TI BQ76922 数据手册 SLUSE86A：https://www.ti.com/lit/ds/symlink/bq76922.pdf

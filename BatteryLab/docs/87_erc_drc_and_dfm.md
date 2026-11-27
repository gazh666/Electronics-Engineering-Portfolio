# 87 ERC、DRC 与 DFM 验证

本文件说明第八阶段如何验证原理图与 PCB，以及本机为什么一项都没跑成。核心纪律：
**没有真实报告就不写"通过"；`COMMAND_OK` 只表示进程正常退出，不等于设计合格。**

## 1. 三种检查的分工

| 检查 | 作用对象 | 回答的问题 | 不能替代什么 |
| --- | --- | --- | --- |
| ERC | 原理图 | 引脚冲突、电源未驱动、悬空、标签/层次端口是否自洽 | 不检查间距、线宽、焊盘几何 |
| DRC | PCB | 间距、线宽、过孔、板边、庭院、丝印、原理图一致性 | 不检查符号逻辑与功能正确性 |
| DFM | 制造数据 | 板厂能不能做、贴片厂能不能贴 | 不证明电气设计正确 |

三者都通过，也只说明"没有触发已配置的规则"，不证明电路功能、热设计或 EMC 合格。
本阶段连三者中的任何一份真实报告都没有，因此全部标 BLOCKED。

## 2. ERC 检查内容与严重级别

| 检查类别 | 典型问题 | 期望处理 |
| --- | --- | --- |
| 引脚冲突 | output 对 output、power_out 对 power_out | 必须消除或加说明 |
| 电源未驱动 | power_in 引脚没有 power_out 来源 | 必须补 PWR_FLAG 或真实电源 |
| 悬空引脚 | 关键引脚未连接 | 逐脚对照引脚映射表 |
| 标签/层次 | 全局标签拼写不一致、层次端口悬空 | 必须修复 |
| 未连接标记 | 有意悬空未加 no-connect | 补标记并记录理由 |
| 库符号问题 | 重复引脚号、隐藏电源脚 | 回到符号层修复 |

严重级别按报告中的 `severity` 统计：`error`、`warning`、`excluded`、`unknown`。
`excluded` 是被人为排除的项，必须单独计数并解释，不能当成"没有"。

未连接项（unconnected）必须来自报告字段 `unconnected_items`。若报告没有该字段，
解析器返回 `NOT_VERIFIED`，不能推断为 0。

## 3. DRC 规则与原理图一致性

`scripts/audit_pcb.py` 调用的命令形式为：

```text
kicad-cli pcb drc --format json --severity-all --schematic-parity \
          --exit-code-violations --output <drc_raw.json> <board.kicad_pcb>
```

| 参数 | 作用 | 为什么必须 |
| --- | --- | --- |
| `--format json` | 机器可读报告 | 人工截图无法审计 |
| `--severity-all` | 输出 warning 与 excluded | 只看 error 会漏掉隐患 |
| `--schematic-parity` | 与原理图网表比对 | 抓"改了原理图没同步 PCB" |
| `--exit-code-violations` | 有违规时返回非零 | 让 CI 能失败 |

规则纪律：

1. 不关闭任何 DRC 规则来"清报告"；如确有例外，走明确排除并记录原因。
2. 线宽、间距、过孔、板边、庭院、丝印、铜到板边都必须启用。
3. 原理图一致性（parity）必须开；它能发现 PCB 上多出/缺少的器件与网络。
4. 目标未连接网络为 0；任何非零都要逐条解释。
5. DRC 通过不等于电气正确，功能仍需实测（见 docs/89）。

## 4. 为什么 COMMAND_OK 不是合格

`eda_tools/kicad_runner.py` 把进程结果分成 `COMMAND_OK`、`COMMAND_NONZERO`、`TIMEOUT`、
`EXECUTION_ERROR`。`COMMAND_OK` 只表示 returncode 为 0：

1. 没加 `--exit-code-violations` 时，有违规也可能返回 0。
2. 命令成功但报告文件为空或结构变化，仍然不是合格。
3. 报告里的 `error` 数量必须由解析器统计，不能靠"命令没报错"。
4. 每次检查必须写入新的 Run ID 目录，禁止复用旧报告冒充本次结果。

因此判定链是：命令状态 → 报告存在 → 报告可解析 → 严重级别计数 → 逐条评审。
任何一环缺失，结论只能是 BLOCKED 或 NOT_VERIFIED。

## 5. 报告解析器设计

`eda_tools/report_parser.py` 的原则是"不认识就说不知道"：

| 输入情况 | 返回 status | reason | 能否判合格 |
| --- | --- | --- | --- |
| 文件不存在 | ERROR | REPORT_MISSING | 否 |
| JSON 损坏/非字典 | ERROR | UNPARSABLE_REPORT | 否 |
| 结构不认识 | NOT_VERIFIED | UNRECOGNIZED_STRUCTURE | 否 |
| 找到 violations 列表 | PARSED | — | 需看计数 |
| 缺 `unconnected_items` | PARSED，但 unconnected 为 NOT_VERIFIED | — | 不能判 0 悬空 |

解析器支持顶层 `violations`/`issues`/`items`，也支持按 sheet 嵌套的结构；
同时统计 `rule_counts`（按 `type` 或 `rule` 聚合）。这样不同 KiCad 版本结构变化时，
不会把未知结构误判成"零错误"。单测覆盖了缺文件、未知结构、正常计数三种情况。本阶段新增
68 个测试全部通过，但这只证明代码行为，不等于 ERC/DRC 通过。

## 6. 原理图审计流水线

`scripts/audit_schematic.py` 的顺序是：

1. 检查引脚映射表完整性：BQ76922 期望 32 脚、BQ24610 期望 24 脚，必须无缺号。
2. 若原理图不存在 → `BLOCKED_NO_SCHEMATIC`。
3. 若无 `kicad-cli` → `BLOCKED_NO_KICAD`。
4. 导出 `kicadxml` 网表；网表没生成 → `BLOCKED_NETLIST_NOT_CREATED`。
5. 解析网表，按 `connection_rule` 逐脚审计：
   `EXACT_NET`、`PRESENT`、`SAME_NET_AS`、`ALLOWED_UNCONNECTED`、`DONTCARE_NET`。
6. `verified != true` 的行一律 `NOT_VERIFIED`，不会自动变 PASS。

网表解析器对结构不符、重复位号、同一引脚出现在两个网络等情况直接抛错，不允许把
未知格式当成"零器件/零网络"。

## 7. 当前 BLOCKED 清单

`validation_summary.json` 记录 9 项 BLOCKED：

| 检查项 | 状态 | 原因 |
| --- | --- | --- |
| kicad_available | BLOCKED | KiCad CLI not found |
| artifact_bms_schematic | BLOCKED | BLOCKED_NO_KICAD_GUI |
| artifact_bms_pcb | BLOCKED | BLOCKED_NO_KICAD_GUI |
| artifact_erc_raw.json | BLOCKED | NOT_PRODUCED |
| artifact_drc_raw.json | BLOCKED | NOT_PRODUCED |
| artifact_schematic.pdf | BLOCKED | NOT_PRODUCED |
| artifact_gerbers | BLOCKED | NOT_PRODUCED |
| artifact_drill | BLOCKED | NOT_PRODUCED |
| artifact_board.step | BLOCKED | NOT_PRODUCED |

板级指标（`pcbnew`）同样不可用，但它没有单列为第 10 项检查，避免重复计数；`board_metrics`
在无 KiCad 时 `pcbnew_available()` 返回 False，指标提取不会被调用。

BLOCKED 不是 PASS。汇总文件同时写明 `hardware_validated = false`、
`production_released = false`。

## 8. DFM 检查项

| 项 | 检查内容 | 当前状态 |
| --- | --- | --- |
| Gerber 层完整性 | 铜层、阻焊、丝印、板框、钻孔图齐全 | 无 Gerber，BLOCKED |
| 钻孔文件 | 孔径表与过孔一致 | 无钻孔，BLOCKED |
| 贴片坐标 | 与 BOM 位号一一对应 | 无坐标，BLOCKED |
| 阻焊/钢网 | 焊盘开窗与钢网开孔 | 无数据 |
| 最小环宽 | 过孔环宽满足板厂能力 | 未选板厂 |
| 板厚/表面处理 | 与订单一致 | 未定义 |
| 拼板与工艺边 | 贴片厂要求 | 未定义 |
| 基准点 | 贴片对位 | 未定义 |
| DNP 与极性 | 与 BOM/装配图一致 | 无 PCB |

导出成功也不等于可投产：`scripts/export_eda_artifacts.py` 在报告中明确写出
"Gerber 导出成功不等于可安全投产；本阶段未做制造评审与硬件验证"。

## 9. 用户装好 KiCad 后的操作步骤

1. 安装 KiCad 并确认 `kicad-cli version` 可执行；本阶段未安装、未提权。
2. 运行 `python -m scripts.verify_kicad --cli "<路径>\kicad-cli.exe"`，记录真实版本与 help 探测。
3. 在图形界面完成原理图，保存 `.kicad_sch`。
4. 在图形界面执行 ERC，导出 JSON；若该版本 CLI 不支持 `sch erc`，必须在 GUI 里导出报告。
5. 运行 `python -m scripts.audit_schematic --cli "<路径>"`，确认 24/32 脚逐脚结果。
6. 完成 PCB 后运行 `python -m scripts.audit_pcb --cli "<路径>"`，得到 DRC 与 parity 报告。
7. 运行 `python -m scripts.export_eda_artifacts --cli "<路径>"` 导出 PDF、Gerber、钻孔、坐标、STEP。
8. 用 `report_parser` 生成的 summary 逐条评审 error/warning/excluded，不得只看 returncode。
9. 所有新报告写入新 Run ID 目录，旧报告不得复用。
10. 只有真实报告 + 人工评审 + 实物验证都完成，才谈得上"合格"。

## 10. 本文件不能支持的结论

- 不能声称"ERC 通过""DRC 通过""0 违规"。
- 不能声称"已生成 Gerber/钻孔/STEP/原理图 PDF"。
- 不能声称"DFM 合格"或"可投产"。
- 不能把 `COMMAND_OK`、导出文件存在、或某个旧运行目录的报告当作本次合格证据。

## 自测题

**1. ERC 与 DRC 各查什么？为什么不能互相替代？**

要点：ERC 查原理图引脚/电源/标签逻辑；DRC 查 PCB 几何与原理图一致性。ERC 不查间距，
DRC 不查符号逻辑。

**2. 为什么 `COMMAND_OK` 不能作为合格判据？**

要点：它只代表进程退出码为 0；未加 `--exit-code-violations` 时违规也可能返回 0，且报告可能缺失或结构变化。

**3. 报告结构不认识时解析器返回什么？为什么？**

要点：`NOT_VERIFIED` / `UNRECOGNIZED_STRUCTURE`。不能在未知结构上返回零错误。

**4. 为什么 `--severity-all` 和 `--schematic-parity` 必须开？**

要点：前者输出 warning/excluded，避免漏隐患；后者抓原理图与 PCB 不同步。

**5. 当前 9 项 BLOCKED 的共同原因是什么？**

要点：本机没有 KiCad（无 `kicad-cli`、无 `.kicad_sch`/`.kicad_pcb`），无法产生真实报告与制造文件。

## 延伸阅读

- KiCad 官方文档（ERC/DRC 与设计规则）：https://docs.kicad.org/
- KiCad 官方下载页：https://www.kicad.org/download/windows/
- KiCad 官方封装库仓库：https://gitlab.com/kicad/libraries/kicad-footprints
- TI BQ24610 数据手册 SLUS892D：https://www.ti.com/lit/ds/symlink/bq24610.pdf
- TI BQ76922 数据手册 SLUSE86A：https://www.ti.com/lit/ds/symlink/bq76922.pdf

# 88 设计评审与 FMEA

本文件汇总第八阶段的设计评审与失效模式分析。评审对象是文档、引脚映射、计算与 BOM，
不是实物板。全部验证状态为 `NOT_EXECUTED` 或 `BLOCKED`，没有任何一项可以读成"已通过"。

## 1. 证据来源

| 文件 | 内容 | 行数/项数 |
| --- | --- | --- |
| `hardware/design_review/schematic_review.csv` | 原理图评审 | 23 项 |
| `hardware/design_review/layout_review.csv` | 布局评审 | 16 项 |
| `hardware/design_review/design_fmea.csv` | 失效模式 | 14 项 |
| `results/eda/run_stage8_20261126_165159_f06bd0/bom.csv` | BOM | 51 行 |
| `validation_summary.json` | 阶段判定 | 10 PASS / 9 BLOCKED / 1 FAIL |

## 2. 原理图评审摘要

23 项的结论分布：

| 结论 | 数量 | 含义 |
| --- | --- | --- |
| PASS | 10 | 文档/计算层面成立 |
| PASS_DESIGN_INTENT | 3 | 方案成立，但实物未生成 |
| ACCEPTED | 1 | 接受为已知边界 |
| MANUAL_REVIEW | 4 | 需人工在 KiCad 或实物上复核 |
| CONDITIONAL | 1 | 有条件通过，依赖器件选型 |
| FAIL | 1 | 已知偏离 |
| NOT_VERIFIED | 1 | 缺少依据 |
| BLOCKED | 2 | 依赖本机无 KiCad |

关键结论：

| 评审项 | 结论 | 依据 |
| --- | --- | --- |
| BQ76922 32 脚 + PAD | PASS | `bms_pin_mapping.csv` 33 行，全 verified |
| BQ24610 24 脚 + PAD | PASS | `charger_pin_mapping.csv` 25 行 |
| 3S 通道映射 | PASS | cell1=VC1/VC0，cell2=VC2/VC1，cell3=VC5/VC4A |
| 未用 VC3A/VC3B | PASS_DESIGN_INTENT | 短接到 VC2，实际连线未生成 |
| 单体 RC 滤波 | PASS | 47 Ω + 0.22 µF，截止 7696 Hz |
| Shunt Kelvin | MANUAL_REVIEW | 无 PCB，无法验证走线 |
| Shunt TC | **FAIL** | WSL2010 为 75 ppm/°C，高于建议 50 ppm/°C |
| 均衡电阻功率 | CONDITIONAL | 最坏 200.6 mW，必须 1206 0.25 W 以上 |
| 保护阈值 | NOT_VERIFIED | 沿用第五阶段教学值，未写入芯片 |
| ERC / 层次 | BLOCKED | 本机无 KiCad |

## 3. 布局评审摘要

16 项中 13 项 BLOCKED、3 项 MANUAL_REVIEW：

| 评审项 | 结论 | 说明 |
| --- | --- | --- |
| 四层叠层 | BLOCKED | 无 PCB 文件 |
| 板框闭合 | BLOCKED | 无 Edge.Cuts |
| 功率路径 | MANUAL_REVIEW | 只有规则，未布线 |
| Kelvin 采样 | BLOCKED | 需实际 PCB |
| 模拟/功率分区 | MANUAL_REVIEW | 仅设计原则 |
| 去耦位置 | BLOCKED | 无 PCB |
| 回流路径 | BLOCKED | 无 PCB |
| 开关节点 PH | BLOCKED | 充电板 PCB 未开始 |
| 热设计 | MANUAL_REVIEW | 仅一阶估算 |
| 测试点 TP1–TP4 | BLOCKED | 无 PCB |
| 元件方向 | BLOCKED | 无 PCB |
| 安装孔 | BLOCKED | 无 PCB |
| 丝印 | BLOCKED | 无 PCB |
| 制造文件 | BLOCKED | 无 Gerber/钻孔/STEP |
| DRC 未连接网络 | BLOCKED | 无 DRC |
| DRC 规则完整性 | BLOCKED | 无 DRC |

## 4. FMEA 方法与 RPN

FMEA 的基本流程：

1. 列出失效模式（本阶段 14 项，见 `design_fmea.csv`）。
2. 分析原因、影响与现有探测手段。
3. 给出设计缓解与验证方法。
4. 由评审组对严重度 S、发生度 O、探测度 D 各打 1–10 分。
5. 计算 RPN = S × O × D，按阈值排序并跟踪整改。

本阶段的诚实边界：`design_fmea.csv` **没有** S/O/D 列，也没有评审组的评分记录。
因此本文件不填任何 RPN 数值，RPN 统一标 **NOT_VERIFIED**。凭空给出 S=7、O=4、D=3
之类的数字会让排序看起来专业，实际不可追溯，违反本阶段纪律。

已有的是定性残余风险（低/中/高）与验证方法。残余风险不是 RPN，不能互相换算。

## 5. 14 项失效模式

所有项的 `verification_status` 均为 `NOT_EXECUTED`。

| 失效模式 | 潜在原因 | 潜在影响 | 探测手段 | 设计缓解 | 残余风险 |
| --- | --- | --- | --- | --- | --- |
| 单体采样开线 | 线束断裂、焊点开裂 | 电芯状态判断错误 | BQ76922 开线检测 + 软件合理性 | 47 Ω + 0.22 µF、连接器防呆 | 中 |
| 采集滤波元件失效 | 电容短路、电阻开路 | 测量异常或通道漂移 | 相邻通道交叉校验 | X7R、1% 电阻、关键通道测试点 | 中 |
| Shunt 采样错误 | Kelvin 走线错误、焊点虚接 | 电流与保护判断偏差 | 库仑计 + 软件阈值双重判断 | Kelvin 独立走线、四端焊盘内侧取样 | 高 |
| MOSFET 短路失效 | 过压/过热击穿 | 保护通路无法切断 | DSG/CHG 回读 + 组端电压突变 | 60 V 器件降额、栅极下拉、保险丝预留 | 高 |
| MOSFET 开路失效 | 键合线或焊点失效 | 无法正常供电 | 负载端掉电检测 | 双管背靠背、功率路径测试点 | 中 |
| 栅极驱动异常 | 驱动回路干扰、下拉失效 | FET 误动作 | CHG/DSG 与电流方向比对 | 10 kΩ 栅源下拉、短回路布局 | 中 |
| NTC 开路 | 连接器脱落 | 温度测量不可用 | ADC 轨值或超范围 | 开路检测、上拉到 REG18 | 低 |
| NTC 短路 | NTC 或线束短路 | 温度读数错误 | 超范围判断 | 短路保护电阻、软件量程检查 | 低 |
| 均衡开关异常 | 内部均衡 FET 损坏 | 非预期电芯放电 | 均衡期间温度与电压监视 | 限制单节同时均衡、均衡电流限流 | 中 |
| 通信异常 | 总线电容过大、上拉错误 | 主机状态不可用 | ALERT 中断 + 超时重试 | 2.2 kΩ 上拉、总线电容预算 | 低 |
| 充电反馈异常 | 分压电阻开路、VFB 漏电 | 充电调节异常 | STAT 状态 + 充电电流监测 | 0.5% 电阻、VFB 远离开关节点 | 中 |
| 输入电源异常 | 适配器过压或反接 | 充电器停机或回灌 | ACOV/UVLO/SLEEP 比较器 | 反向阻断 PFET、输入 TVS 评估 | 中 |
| 功率器件温升过高 | 铜皮不足、环境温度高 | 可靠性下降 | 一阶热估算、后续热像仪 | 降额设计、散热铜皮 | 中 |
| PCB 连接错误 | 原理图与 PCB 不一致 | 功能异常或器件损坏 | DRC parity + 逐网络审计 | 网表驱动布线、逐网络审计 | 中 |

## 6. 残余风险汇总

| 等级 | 数量 | 失效模式 |
| --- | --- | --- |
| 高 | 2 | Shunt 采样错误、MOSFET 短路失效 |
| 中 | 9 | 采样开线、滤波失效、MOSFET 开路、栅极异常、均衡异常、充电反馈、输入异常、温升、PCB 连接 |
| 低 | 3 | NTC 开路、NTC 短路、通信异常 |

两项"高"风险的共同点：都会让保护或计量失去可信度，且无法靠软件完全兜底。

1. **Shunt 采样错误**：10 mΩ 上 2.5 A 只有 25 mV，Kelvin 走线或焊点问题会直接变成
   电流增益误差。缓解手段是四端取样与独立走线，但必须制板后实测才能关闭。
2. **MOSFET 短路失效**：保护开关短路后，过充/过流无法切断。当前只有器件降额与栅极
   下拉，缺少保险丝实物与失效实测，残余风险保持"高"。

## 7. 可追溯性

| 追溯对象 | 记录位置 | 说明 |
| --- | --- | --- |
| 器件规格 | `component_database.csv` | 每个 critical 器件含数据手册 URL、版本、页码 |
| 引脚定义 | `*_pin_mapping.csv` | 每行含 source_document、source_page、verified |
| 计算结果 | `design_calculations.json` | 含公式字符串与 sources |
| 阶段判定 | `validation_summary.json` | 10 PASS / 9 BLOCKED / 1 FAIL |
| 产物完整性 | `release_manifest.json` | 12 个文件，逐文件 SHA-256 |
| BOM | `bom.csv` | 51 行，critical 10 个全部 VERIFIED_DATASHEET |

可追溯性的最低要求是：任何一个数字都能回到"哪份文档、哪一页、哪条公式、哪个 Run ID"。
做不到这一点的数字不应出现在评审结论里。

## 8. 未关闭项与评审结论

| 未关闭项 | 状态 | 关闭条件 |
| --- | --- | --- |
| Shunt TC 偏离 | FAIL | 换 ≤50 ppm/°C 器件或做温度校准并验证 |
| LC 谐振 11.07 kHz | FAIL | 改电感/电容或取得 DC Bias 曲线后实测 |
| 30 V FET 与 ACOV 32 V | MANUAL_REVIEW | 评估 40 V 器件或输入钳位 |
| 反馈分压偏置电流 | NOT_VERIFIED | 查数据手册电气特性或实测 |
| 保护阈值写入芯片 | NOT_VERIFIED | 配置 OTP/寄存器并回读验证 |
| ERC/DRC/DFM | BLOCKED | 安装 KiCad 并产生真实报告 |
| 全部实物验证 | NOT_EXECUTED | 按 docs/89 执行 |

评审结论：设计在文档与计算层面自洽，但存在 1 个 LC FAIL、1 个 Shunt TC FAIL、多个
MANUAL_REVIEW 与全部实物项未执行。当前只能作为"可进入制板前评审"的工程原型，
不能作为可投产或已验证的设计。

## 自测题

**1. 为什么本文件不填 RPN 数值？**

要点：`design_fmea.csv` 没有 S/O/D 评分与评审记录；凭空打分不可追溯。RPN 标 NOT_VERIFIED，
只保留定性残余风险。

**2. 两项高风险失效模式是什么？为什么高？**

要点：Shunt 采样错误与 MOSFET 短路。前者让电流/保护失真且难靠软件兜底，后者让保护
无法切断通路。

**3. 原理图评审 23 项里唯一的 FAIL 是什么？**

要点：分流电阻 WSL2010 的 TC 为 75 ppm/°C，高于 BQ76922 建议的 ≤50 ppm/°C。

**4. PASS 与 PASS_DESIGN_INTENT 有什么区别？**

要点：PASS 是文档/计算层面已成立；PASS_DESIGN_INTENT 只表示方案成立，实物连线或布局尚未生成。

**5. 可追溯性最低要求是什么？**

要点：每个数字能回到文档、页码、公式与 Run ID；产物还要有哈希清单。

## 延伸阅读

- TI BQ76922 数据手册 SLUSE86A：https://www.ti.com/lit/ds/symlink/bq76922.pdf
- TI BQ24610 数据手册 SLUS892D：https://www.ti.com/lit/ds/symlink/bq24610.pdf
- TI CSD18540Q5B 数据手册 SLPS488B：https://www.ti.com/lit/ds/symlink/csd18540q5b.pdf
- Vishay WSL 数据手册 Document 30100：https://www.vishay.com/docs/30100/wsl.pdf
- KiCad 官方文档：https://docs.kicad.org/

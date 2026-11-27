# 62 BQ24610 参考设计研究

本文件是硬件参考研究，全部 BQ24610 数值标注为 `datasheet_specification`，
没有任何一项来自本项目实测。

## 1. 关键规格

| 项 | 值 | 性质 |
| --- | --- | --- |
| 输入电压 | 5–28 V | datasheet_specification |
| 电池节数 | 1–6 节 | datasheet_specification |
| 最大充电电流 | 10 A（取决于外部器件） | datasheet_specification |
| 开关频率 | 600 kHz | datasheet_specification |
| 拓扑 | 同步降压，集成高/低边驱动 | datasheet_specification |
| 电压调节精度 | 0.5% 量级 | datasheet_specification |
| 封装 | 24 引脚 VQFN（RGE） | datasheet_specification，引脚号需复核 |
| 输入限流 | ACSET 可编程 | datasheet_specification |
| 终止 | 终止电流 + 安全定时 | datasheet_specification |
| 温度检测 | TS + 外部 NTC | datasheet_specification |

## 2. 与本项目 SPICE 模型的逐项差异

| 项 | 本项目 | BQ24610 | 影响 |
| --- | --- | --- | --- |
| 频率 | 100 kHz | 600 kHz | 纹波、环路带宽、电感量级都不同 |
| 低边 | 二极管 | 同步 NFET | 效率分布不同，不能互相外推 |
| 输入隔离 | 无 | ACFET | C07/C20 的反向电流结论不可移植 |
| 电池隔离 | 无 | BATDRV | 保护断开后的行为未建模 |
| 控制器 | 网表行为源 PI | 内部跨导放大器 + 外部补偿 | 补偿设计方法不同 |
| 保护执行 | 许可判定 + 波形核查 | 真实 FET 开断 | 本阶段未验证电气重分布 |
| 电池模型 | 3S 一阶 RC | 真实电芯 | SOC 外推限制不同 |

## 3. 初步选型

见 `hardware/charger/charger_preliminary_bom.csv`。关键点：

- 10 µH / 3 A 电感（600 kHz 量级），不是本项目的 100 µH；
- 22 µF × 2 陶瓷输出电容，不是 220 µF 电解；
- 需要 ACFET、BATDRV FET、检流电阻、NTC、自举与补偿网络；
- 所有器件值标记 `preliminary`，必须在原理图评审时按数据手册重算。

## 4. 若要进入硬件阶段

1. 按数据手册确认 24 引脚定义、热焊盘、功率回路与地分割；
2. 用厂商模型重做效率、温升与环路；
3. 加入 ACFET/BATDRV 后重跑输入掉电与反向电流；
4. 计算 ISET/TTC/VFB 电阻电容的容差与温漂；
5. 在硬件上测量恒压精度、终止电流、保护响应时间；
6. 重新评估 C11 类过压风险（当前恒压目标下不会由不一致触发）。

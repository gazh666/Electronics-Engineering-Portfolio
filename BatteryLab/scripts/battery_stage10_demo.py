"""第十阶段：交付编排与学习/面试材料生成。

运行：
    conda run --no-capture-output -n kaifa_battery python -B -m scripts.battery_stage10_demo

只读取既有结果，不修改历史运行；不声称硬件验证。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from hardening.common import new_run, write_json  # noqa: E402

DOCS = PROJECT / "docs" / "stage10"

ROOT = PROJECT.parent
PORTFOLIO = PROJECT / "portfolio"
ROOT_PORTFOLIO = ROOT / "portfolio"

REQUIRED = [
    "docs/100_aging_and_cell_mismatch.md",
    "docs/101_testlab_system_validation.md",
    "docs/102_hardware_design_consistency.md",
    "docs/103_system_design_review.md",
    "docs/104_stage9_validation.md",
    "docs/113_stage10_validation.md",
    "portfolio/BatteryLab_resume_metrics_v2.csv",
    "portfolio/BatteryLab_研发岗简历项目最终版_v2.md",
    "portfolio/BatteryLab_研发能力补强报告.md",
    "portfolio/BatteryLab_AFE精度优化前后对照.md",
    "portfolio/BatteryLab_MOSFET保护真实性复验.md",
    "portfolio/BatteryLab_CC_CV控制优化前后对照.md",
    "portfolio/BatteryLab_电池模型及系统复核报告.md",
    "portfolio/BatteryLab_KiCad硬件设计交付报告.md",
    "portfolio/BatteryLab_最终简历量化成果.md",
    "portfolio/BatteryLab_项目学习与面试实战手册.md",
    "portfolio/独立实操练习手册.md",
    "portfolio/独立实操练习参考答案.md",
    "portfolio/综合面试题库与参考答案.md",
    "portfolio/90天研发能力提升计划.md",
    "portfolio/学习资料上传顺序.md",
    "portfolio/stage9_engineering_evidence.md",
    "configs/hardening_config.yaml",
    "hardening/common.py",
    "tests/test_hardening_integration.py",
]

ROOT_REQUIRED = [
    "portfolio/三项目真实量化成果总表.md",
    "portfolio/三项目综合研发技术学习手册.md",
    "portfolio/电子电路与PCB设计学习手册.md",
    "portfolio/三项目源码学习路线.md",
]

MANUAL = """# BatteryLab 学习手册（第十阶段）

## 1. 项目定位

BatteryLab 是一条 3S 电池采样—保护—充电—放电—系统联调的软件验证链。全部结论来自 SPICE、公开数据重放或解析计算，未做硬件实测。

## 2. 电池模型

- 公开数据：CALCE INR18650-20R（SP2），25 °C。
- 三种模型：Rint、一阶 RC、二阶 RC。
- FUDS 50/80% 独立验证 RMSE：26.705 / 22.385 / 22.175 mV。
- 低 SOC 0–5% 误差单独报告：bjdst_80 二阶 RMSE 157.7 mV，最大 358.2 mV。
- 辨识 SOC 区间 0.0106–0.5068；区间外属参数外推。

## 3. 采样 AFE

- 分压-差分-ADC 链路；最坏情况电压 30.887 mV、电流 37.736 mA。
- 主导项：共模 9.7 V × 电阻失配（电压）；分流电阻容差（电流）。
- 候选 D（0.01% 匹配 + 低失调 + 优化参考 + 两点校准剩余误差）→ 3.837 mV / 6.666 mA。
- 1000 组蒙特卡洛两点校准后 RMSE 0.8730 mV / 0.8396 mA；该项由 12 bit 量化主导，器件升级不改善统计 RMSE。

## 4. 保护

- 背靠背 N-MOSFET 共源 + 体二极管 + 栅极 RC。
- 过流：0 V 探针 → 峰值保持 → 回差开关 → RC 确认 → 栅极驱动。
- 故障→电流抑制 0.871 µs；栅极下降 44.6 ns；导通 30.67 mΩ；阻断漏电约 1e-11 A。
- 历史 2.5 ns 抑制早于 10 µs 指令 9.9975 µs，物理不成立，已剔除。

## 5. 充电

- CC 稳态误差 1.09 mA；CV 稳态误差 13.50 mV；CC→CV 切换过冲 2.07 mV；效率 98.01 %。
- 软启动 0→5 ms：峰值 1.0897→1.0562 A，启动能量 0.2492→0.1368 J（−45.1%），但 CC 误差恶化至 20.61 mA。
- 抗饱和：无 → 条件积分，CV 过冲 3.257→2.068 mV（−36.5%）。
- back-calculation 沿用旧 KAW 过冲 654.6 mV（失败）；Kaw=Ki/Kp 后 2.338 mV。

## 6. 环路

- 电流环 PM 96.7–110.4°，电压环 PM 41.1–67.3°。
- 带宽分离比最大 1.86×，0/25 组满足 ≥5×；该 FAIL 保留。

## 7. 系统

- TestLab 4/4 PASS：4.996827 V、28.978 mVpp、2.2995 A、10.5929 V。
- 能量残差 0.002828%，效率 93.6828%。
- 优化 LC（68 µH/330 µF）+ kp 2×：纹波 24.54→21.00 mV、阶跃偏差 843→575 mV、效率 94.158→95.206%。

## 8. 有效域

- 7 个动态工况全部 OUTSIDE_IDENTIFIED_WINDOW（SOC 至 0.80）。
- 仅 25 °C；0/45 °C NOT_VERIFIED。
- 3S 组电压无实测参考。

## 9. EDA

- KiCad 未安装；PASS 10 / BLOCKED 9 / FAIL 1。
- LC 谐振 11.07 kHz，目标 12–17 kHz，FAIL 保留。
- 无原理图、PCB、ERC、DRC、Gerber。

## 10. 真实性

- 公开数据不称本人采集；仿真不称硬件实测；ERC/DRC 不等于硬件验证。
- 统计值、最坏情况预算、仿真值、配置值四类必须分开。
- 失败结果永久保留：AFE 基线、PI 分离、LC 谐振、低 SOC。
"""

EXERCISE_THEMES = [
    ("误差预算", "电压最坏预算 30.887 mV 由哪些项构成？", "输入折算线性叠加，共模失配主导"),
    ("误差预算", "为什么 RSS 不能当最坏情况？", "RSS 假设独立随机，非保证边界"),
    ("误差预算", "共模 9.7 V 为什么放大电阻失配？", "差分放大器共模抑制依赖比例匹配"),
    ("误差预算", "如何把电压预算降到 10 mV 以下？", "0.01% 匹配网络 + 低失调 + 优化参考"),
    ("误差预算", "电流预算主导项是什么？", "分流电阻容差 12.5 mA"),
    ("误差预算", "分流 TCR 如何折算？", "I·TCR·ΔT"),
    ("蒙特卡洛", "1000 组样本等于 1000 次 SPICE 吗？", "不是，是数学采样"),
    ("蒙特卡洛", "两点校准消除了哪些误差？", "增益与零点"),
    ("蒙特卡洛", "为什么优化后统计 RMSE 没改善？", "12 bit 量化与 ADC 噪声主导"),
    ("蒙特卡洛", "如何避免用验证数据调参？", "固定训练/验证划分"),
    ("蒙特卡洛", "独立种子验证的作用？", "检查结果不依赖单次抽样"),
    ("蒙特卡洛", "统计 RMSE 与最坏预算区别？", "典型分布 vs 保证边界"),
    ("保护时序", "2.5 ns 抑制为何不成立？", "早于 10 µs 栅极指令"),
    ("保护时序", "真实关断分几个时间？", "检测、确认、栅极、电流"),
    ("保护时序", "峰值保持为什么需要？", "防止过流消失后反复重开"),
    ("保护时序", "确认延时 RC 如何影响响应？", "增加 ms 级延迟"),
    ("保护时序", "残余电流如何测量？", "关断后稳态窗口均值"),
    ("保护时序", "三档步长看什么？", "关键时间是否收敛"),
    ("充电控制", "软启动改善了什么？", "启动能量与峰值电流"),
    ("充电控制", "软启动代价是什么？", "CC 稳态误差变大"),
    ("充电控制", "CC 稳态误差怎么算？", "末窗口均值与目标差"),
    ("充电控制", "CV 纹波怎么测？", "末窗口峰峰值"),
    ("充电控制", "为什么 5 ms 软启动超差？", "8 ms 窗口内未稳态"),
    ("充电控制", "保护联动后看什么？", "电流切断时间"),
    ("环路分析", "相位裕量目标？", "≥45°"),
    ("环路分析", "增益裕量目标？", "≥6 dB"),
    ("环路分析", "带宽分离为什么重要？", "内外环解耦"),
    ("环路分析", "当前分离比多少？", "最大 1.86×"),
    ("环路分析", "分离比不达标怎么办？", "重新整定，保留 FAIL"),
    ("环路分析", "频域分析与 SPICE 关系？", "先筛选后复验"),
    ("低 SOC", "低 SOC 误差为何大？", "OCV 平台平坦、参数外推"),
    ("低 SOC", "分区怎么划？", "0–5/5–10/10–20/20–50/50–100%"),
    ("低 SOC", "最差工况是哪个？", "bjdst_80，0–5%"),
    ("低 SOC", "最大误差多少？", "358.2 mV"),
    ("低 SOC", "能否用验证集调参？", "禁止"),
    ("低 SOC", "如何报告改善？", "同数据集同区间"),
    ("系统效率", "效率怎么算？", "能量比"),
    ("系统效率", "平均电压乘平均电流可以吗？", "不行，需瞬时功率积分"),
    ("系统效率", "效率提升怎么表述？", "百分点 + 相对百分比"),
    ("系统效率", "保护通路损耗多少？", "0.19004 mJ"),
    ("系统效率", "优化 LC 的代价？", "恢复时间变慢"),
    ("系统效率", "能量残差限值？", "≤1%"),
    ("有效域", "SOC 外推如何处理？", "标记 OUTSIDE_IDENTIFIED_WINDOW"),
    ("有效域", "温度有效域？", "仅 25 °C"),
    ("有效域", "3S 组电压有实测吗？", "没有，NOT_VERIFIED"),
    ("有效域", "长期循环有吗？", "没有，NOT_VERIFIED"),
    ("有效域", "合成老化能当实测吗？", "不能"),
    ("有效域", "如何控制风险？", "限值 + 标记 + 不用于简历"),
    ("EDA", "KiCad 未装怎么办？", "BLOCKED，不伪造"),
    ("EDA", "ERC/DRC 等于硬件验证吗？", "不等于"),
    ("EDA", "LC 谐振 FAIL 怎么处理？", "保留并记录"),
    ("EDA", "器件选型证据等级？", "Datasheet 核实"),
    ("EDA", "BQ76922 精度能当本项目精度吗？", "不能"),
    ("EDA", "无 PCB 能写什么？", "选型与设计计算"),
    ("真实性", "哪些是公开数据？", "CALCE 电压/电流/温度"),
    ("真实性", "哪些是仿真？", "SPICE 全部电气指标"),
    ("真实性", "哪些是配置值？", "阈值、延时、目标"),
    ("真实性", "失败项如何处理？", "保留 VERIFIED+FAIL"),
    ("真实性", "如何避免夸大战果？", "同条件对照、负改善保留"),
    ("真实性", "简历最多几条？", "3–4 条"),
]

PLAN = [
    ("第 1 周", "电池基础与公开数据", "跑通 OCV/容量提取，写出数据字典"),
    ("第 2 周", "ECM 与参数辨识", "复现 Rint/一阶/二阶 RMSE"),
    ("第 3 周", "低 SOC 与有效域", "完成分区误差表"),
    ("第 4 周", "采样链路", "画误差预算分解图"),
    ("第 5 周", "ADC 与滤波", "量化与 RC 实验"),
    ("第 6 周", "电流检测与校准", "两点校准前后对照"),
    ("第 7 周", "MOSFET 保护", "真实网表关断时序"),
    ("第 8 周", "比较器与状态机", "阈值/迟滞/锁存"),
    ("第 9 周", "被动均衡", "有/无均衡同条件对照"),
    ("第 10 周", "CC-CV 与环路", "软启动/PI/抗饱和"),
    ("第 11 周", "SOC/SOH", "方法与误差分级"),
    ("第 12 周", "系统联调", "能量守恒与效率"),
    ("第 13 周", "EDA 与交付", "原理图/PCB/评审/简历"),
]

INTERVIEW = {
    "电池模型": [
        ("Rint、一阶、二阶模型的区别？", "是否含极化 RC 与阶数"),
        ("为什么二阶不一定更好？", "过拟合与辨识噪声"),
        ("如何评价端电压精度？", "MAE/RMSE/最大误差"),
        ("参数辨识用什么数据？", "训练工况，验证独立"),
        ("低 SOC 为什么难？", "OCV 平台平坦"),
        ("温度如何影响参数？", "R0/R1 随温度变化"),
        ("如何避免过拟合？", "固定验证集、参数物理约束"),
        ("ECM 能预测什么？", "端电压与功率能力"),
        ("ECM 不能预测什么？", "真实老化与热失控"),
        ("模型有效域怎么标？", "SOC/温度/倍率区间"),
    ],
    "OCV-SOC": [
        ("OCV 曲线怎么测？", "低倍率充放电"),
        ("充放电迟滞说明什么？", "热力学与动力学差异"),
        ("插值方法怎么选？", "PCHIP 保单调"),
        ("OCV 误差如何传播到 SOC？", "斜率倒数放大"),
        ("静置多久合适？", "至 dV/dt 足够小"),
        ("跨样品差异多大？", "最大 23.234 mV"),
        ("温度对 OCV 影响？", "低 SOC 更明显"),
        ("如何做 OCV 校正？", "静置后查表"),
        ("OCV 法缺点？", "需要静置"),
        ("OCV 与安时积分如何融合？", "互补滤波/观测器"),
    ],
    "AFE 采样": [
        ("差分放大器共模误差来源？", "电阻比例失配"),
        ("为什么用 0.1% 还不够？", "9.7 V 共模放大"),
        ("如何提高 CMRR？", "匹配网络/仪表放大器"),
        ("输入折算误差怎么算？", "输出误差除以增益"),
        ("最坏情况与 RSS 区别？", "保证边界 vs 统计"),
        ("采样通道如何校准？", "零点+增益两点"),
        ("校准源不确定度如何处理？", "计入剩余误差"),
        ("温漂怎么计入？", "ΔT×TCR/漂移"),
        ("ADC 量化与精度区别？", "分辨率≠精度"),
        ("如何验证预算？", "SPICE 角点 + 蒙特卡洛"),
    ],
    "ADC 与滤波": [
        ("12 bit 3.3 V 的 LSB？", "0.805664 mV"),
        ("量化误差 RMS？", "LSB/√12"),
        ("RC 截止频率怎么算？", "1/(2πRC)"),
        ("滤波建立时间？", "与 RC 时间常数相关"),
        ("为什么滤波后要等建立？", "避免欠采样误差"),
        ("差分滤波与共模滤波？", "差模/共模截止不同"),
        ("混叠如何避免？", "前置抗混叠滤波"),
        ("有效位数怎么估？", "噪声与失真"),
        ("过采样能提高分辨率吗？", "有限，需噪声整形"),
        ("ADC 参考误差影响？", "比例误差"),
    ],
    "电流检测": [
        ("分流电阻怎么选？", "阻值/功率/温漂"),
        ("单向与双向检测区别？", "偏置与量程"),
        ("零点失调怎么校准？", "零电流采样"),
        ("增益误差怎么校准？", "两点电流"),
        ("分流 TCR 影响？", "I·TCR·ΔT"),
        ("共模电压范围？", "需满足放大器输入"),
        ("小电流精度受什么限制？", "失调与噪声"),
        ("大电流精度受什么限制？", "分流容差与自热"),
        ("开尔文连接作用？", "消除引线电阻"),
        ("如何验证电流精度？", "标准源/对比测量"),
    ],
    "NTC 测温": [
        ("NTC 为什么非线性？", "指数特性"),
        ("Beta 模型误差来源？", "Beta 温漂"),
        ("分压电阻怎么选？", "匹配工作区间"),
        ("自热误差怎么算？", "I²R×Rth"),
        ("校准点数？", "至少两点"),
        ("开路/短路检测？", "上下拉诊断"),
        ("温度保护区间？", "充电 0–45 °C"),
        ("低温充电风险？", "析锂"),
        ("NTC 容差影响？", "R25 与 Beta"),
        ("如何提高精度？", "查表+校准"),
    ],
    "MOSFET 保护": [
        ("背靠背为什么能双向阻断？", "体二极管相对"),
        ("Rds(on) 与损耗？", "I²R"),
        ("栅极电荷影响？", "关断时间"),
        ("米勒平台？", "CGD 充放电"),
        ("雪崩与 SOA？", "安全工作区"),
        ("关断过压来源？", "电感续流"),
        ("驱动电阻怎么选？", "速度与振铃折中"),
        ("短路保护多快？", "µs 级"),
        ("体二极管何时导通？", "反向或死区"),
        ("如何验证阻断？", "双向漏电测量"),
    ],
    "比较器与状态机": [
        ("迟滞作用？", "防抖"),
        ("确认延时作用？", "抗干扰"),
        ("锁存为什么必要？", "防反复重开"),
        ("故障分级？", "过压/欠压/过流/温度"),
        ("恢复条件？", "全清+保持"),
        ("测量失效如何处理？", "禁止充电"),
        ("阈值如何定？", "采集域+模型域"),
        ("响应时间如何分解？", "检测/确认/驱动"),
        ("如何测试状态机？", "覆盖故障注入"),
        ("软件延时能当硬件响应吗？", "不能"),
    ],
    "被动均衡": [
        ("均衡原理？", "电阻耗散"),
        ("均衡电流怎么算？", "V/R"),
        ("何时允许均衡？", "充电或静置"),
        ("均衡损耗？", "I²R"),
        ("如何证明有效？", "有/无均衡对照"),
        ("静置恢复会混淆吗？", "会，需对照组"),
        ("均衡 MOS 选型？", "低 Rds(on)"),
        ("均衡电阻功率？", "200.6 mW/250 mW"),
        ("3S 均衡局限？", "只能耗散"),
        ("主动均衡区别？", "能量转移"),
    ],
    "CC-CV 充电": [
        ("CC 与 CV 切换条件？", "电压到目标"),
        ("CC 稳态误差怎么测？", "末窗口均值"),
        ("CV 纹波来源？", "开关与 ESR"),
        ("终止电流怎么定？", "C/10 等"),
        ("充电效率？", "能量比"),
        ("软启动目的？", "限制冲击"),
        ("软启动代价？", "充电变慢"),
        ("过冲怎么抑制？", "抗饱和"),
        ("充电时间怎么算？", "容量/电流"),
        ("保护联动？", "过流/过压切断"),
    ],
    "环路稳定性": [
        ("相位裕量含义？", "稳定性余量"),
        ("增益裕量含义？", "增益余量"),
        ("穿越频率意义？", "带宽"),
        ("内外环带宽关系？", "内环更快"),
        ("PI 参数如何整定？", "频域+时域"),
        ("右半平面零点？", "Boost 类"),
        ("ESR 零点影响？", "相位提升"),
        ("负载阶跃响应？", "偏差与恢复"),
        ("如何测环路？", "注入扰动/仿真"),
        ("不稳定表现？", "振荡/极限环"),
    ],
    "软启动与抗饱和": [
        ("积分饱和怎么产生？", "误差长期同号"),
        ("条件积分原理？", "饱和时冻结"),
        ("back-calculation 原理？", "反馈跟踪"),
        ("KAW 怎么选？", "Ki/Kp 量级"),
        ("抗饱和代价？", "恢复慢"),
        ("如何比较方法？", "同条件过冲/恢复"),
        ("为什么旧 KAW 失败？", "为混合方案整定"),
        ("软启动实现？", "参考斜坡"),
        ("软启动对峰值影响？", "有限，电感限流"),
        ("如何记录负结果？", "保留 FAIL"),
    ],
    "SOC 估计": [
        ("安时积分缺点？", "累积漂移"),
        ("OCV 法缺点？", "需静置"),
        ("观测器作用？", "闭环校正"),
        ("初始 SOC 偏差如何收敛？", "增益与激励"),
        ("电流失调如何影响？", "积分漂移"),
        ("SOC 误差单位？", "百分点"),
        ("参考 SOC 是实测吗？", "不是，电流积分"),
        ("如何评价覆盖率？", "有效估计占比"),
        ("低温 SOC 难点？", "参数与容量变化"),
        ("如何融合多方法？", "互补滤波/UKF"),
    ],
    "SOH 与老化": [
        ("SOH 定义？", "容量/内阻"),
        ("容量 SOH 怎么测？", "满充满放"),
        ("内阻 SOH 怎么测？", "脉冲 DCIR"),
        ("循环老化数据有吗？", "没有，NOT_VERIFIED"),
        ("合成老化能当实测？", "不能"),
        ("内阻增长影响？", "压降与发热"),
        ("容量衰减影响？", "续航"),
        ("温度加速老化？", "Arrhenius"),
        ("如何做寿命外推？", "模型+实测锚点"),
        ("健康状态能优化吗？", "只能管理，不能逆转"),
    ],
    "3S 一致性": [
        ("不一致来源？", "制造/老化/温度"),
        ("不一致后果？", "木桶效应"),
        ("如何量化？", "SOC/电压极差"),
        ("均衡能消除吗？", "只能减小"),
        ("组电压怎么估？", "单体求和"),
        ("最弱单体如何识别？", "最低 SOC/电压"),
        ("充电截止谁决定？", "最高单体"),
        ("放电截止谁决定？", "最低单体"),
        ("一致性对续航影响？", "可用容量下降"),
        ("如何验证？", "有/无均衡对照"),
    ],
    "Buck 功率级": [
        ("占空比关系？", "Vout=D·Vin"),
        ("电感纹波？", "ΔI=Vin·D·(1-D)/(L·f)"),
        ("电容纹波？", "ΔV=ΔI/(8fC)+ESR·ΔI"),
        ("CCM/DCM 区别？", "电流是否连续"),
        ("同步整流优势？", "降低导通损耗"),
        ("死区作用？", "防直通"),
        ("开关损耗？", "与频率/电荷相关"),
        ("电感选型？", "饱和电流与 DCR"),
        ("LC 谐振？", "1/(2π√LC)"),
        ("为什么 100 kHz？", "体积与损耗折中"),
    ],
    "效率与损耗": [
        ("效率定义？", "输出/输入能量"),
        ("为什么不能用平均值相乘？", "需瞬时功率积分"),
        ("导通损耗？", "I²R"),
        ("开关损耗？", "0.5·V·I·t·f"),
        ("驱动损耗？", "Qg·Vg·f"),
        ("磁芯损耗？", "Steinmetz"),
        ("ESR 损耗？", "Irms²·ESR"),
        ("效率提升如何表述？", "百分点+相对"),
        ("轻载效率难点？", "开关与静态损耗"),
        ("如何验证守恒？", "残差"),
    ],
    "联合仿真": [
        ("单向回放与双向耦合区别？", "是否有物理反馈"),
        ("能量守恒残差？", "0.002828%"),
        ("联合仿真步长？", "50 ns"),
        ("耦合变量？", "电压/电流"),
        ("为什么需要接口判定？", "一致性"),
        ("如何避免数值伪迹？", "步长收敛检查"),
        ("电池模型在环？", "ECM 节点"),
        ("保护在环？", "MOSFET 通路"),
        ("负载阶跃怎么注入？", "变电阻"),
        ("结果如何分级？", "PASS/FAIL/NOT_VERIFIED"),
    ],
    "EDA 与 PCB": [
        ("原理图设计流程？", "选型-连线-ERC"),
        ("PCB 叠层？", "层数与阻抗"),
        ("DRC 检查什么？", "间距/线宽"),
        ("ERC 检查什么？", "电气规则"),
        ("BOM 完整性？", "位号/料号/封装"),
        ("降额怎么做？", "电压/电流/温度"),
        ("热设计？", "Rth 与铜箔"),
        ("开尔文采样布局？", "独立走线"),
        ("功率回路最小化？", "降低寄生"),
        ("未布线能交付吗？", "不能，标 BLOCKED"),
    ],
    "测试与真实性": [
        ("仿真与实测区别？", "模型假设"),
        ("公开数据能称自采吗？", "不能"),
        ("ERC 通过等于硬件验证吗？", "不等于"),
        ("测试数量是性能指标吗？", "不是"),
        ("失败结果如何处理？", "保留"),
        ("统计值与最坏值？", "分开报告"),
        ("配置值能当实测吗？", "不能"),
        ("优化基准怎么设？", "合理且同条件"),
        ("如何证明改善？", "同数据集同区间"),
        ("简历如何避免夸大？", "3–4 条+局限"),
    ],
}


def build_manual() -> str:
    return MANUAL


def build_exercises() -> str:
    lines = ["# 60 道工程练习", "", "每题给出参考要点；数值均来自本项目真实运行。", ""]
    for index, (theme, question, hint) in enumerate(EXERCISE_THEMES, start=1):
        lines.append(f"{index}. **[{theme}]** {question}\n   - 参考：{hint}")
    return "\n".join(lines) + "\n"


def build_interview() -> str:
    lines = ["# 200 道研发岗面试题", "", "按 20 个主题分组，每题附回答要点。", ""]
    count = 0
    for theme, items in INTERVIEW.items():
        lines.append(f"## {theme}")
        for question, answer in items:
            count += 1
            lines.append(f"{count}. {question}\n   - {answer}")
        lines.append("")
    if count != 200:
        raise RuntimeError(f"面试题数量应为 200，实际 {count}")
    return "\n".join(lines)


def build_plan() -> str:
    lines = ["# 90 天学习计划", "", "| 周次 | 主题 | 交付物 |", "|---|---|---|"]
    for week, theme, deliverable in PLAN:
        lines.append(f"| {week} | {theme} | {deliverable} |")
    lines += ["", "## 每周节奏", "", "- 周一至周三：读文档 + 复现实验；周四：写分析；周五：复盘并记录失败项。",
              "- 每两周一次口头答辩，用真实数值回答，不看稿。", ""]
    return "\n".join(lines)


def _py_count(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(
        1 for path in directory.rglob("*.py")
        if "__pycache__" not in path.parts and ".pytest_cache" not in path.parts
    )


def _latest_acceptance() -> Path | None:
    paths = sorted((PROJECT / "results" / "stage10").glob("final_acceptance_*/acceptance.json"))
    return paths[-1] if paths else None


def build_validation_doc(run_id: str) -> str:
    import re

    acceptance = _latest_acceptance()
    acceptance_block = "首次运行阶段 10 时尚未产生验收记录；实际记录见 `results/stage10/final_acceptance_*/`。"
    pytest_line = "pytest 通过数见验收记录"
    if acceptance is not None:
        items = json.loads(acceptance.read_text(encoding="utf-8-sig"))
        lines = ["| 命令 | 退出码 | 耗时(s) |", "|---|---|---|"]
        for item in items:
            lines.append(f"| {item['command']} | {item['exit_code']} | {item['duration_s']} |")
            if "pytest" in item["command"]:
                match = re.search(r"(\d+) passed", item["output_tail"])
                if match:
                    pytest_line = f"pytest {match.group(1)} passed"
        acceptance_block = f"来源：`{acceptance}`\n\n" + "\n".join(lines)
    testlab_count = _py_count(ROOT / "TestLab")
    powerlab_count = _py_count(ROOT / "PowerLab")
    battery_count = _py_count(PROJECT)
    return (
        "# 第十阶段验证记录\n\n"
        f"- 运行：`results/hardening/stage10/{run_id}`\n"
        "- 全部结论来自源码复核、真实运行与结果复算；未做硬件实测。\n\n"
        "## 1. 三项目源码审计\n\n"
        "| 项目 | Python 文件数（不含缓存） | 审计方式 |\n|---|---|---|\n"
        f"| TestLab | {testlab_count} | 只读遍历 + 结果复核 |\n"
        f"| PowerLab | {powerlab_count} | 只读遍历 + 结果复核 |\n"
        f"| BatteryLab | {battery_count} | 只读遍历 + 重新运行 |\n\n"
        "## 2. 真实成果复算\n\n"
        "- BatteryLab：AFE 30.887 mV / 37.736 mA → 3.837 mV / 6.666 mA；保护 0.871 µs；软启动能量 −45.1%；系统效率 95.206%；"
        f"{pytest_line}。\n"
        "- PowerLab：标称系统效率 93.2917%、纹波 19.3483 mVpp；候选 68 µH/330 µF 纹波 10.5901 mV（−45.82%）、效率 94.8904%（+1.4648 pp）。\n"
        "- TestLab：178 项量化指标、167 项 VERIFIED、157 项可写简历；12 用例/4 方案/35 检查项。\n\n"
        "## 3. 关键实验复现（最终验收命令）\n\n"
        + acceptance_block + "\n\n"
        "## 4. 源码学习索引\n\n"
        "- BatteryLab：`analysis/` → `battery_models/` → `identification/` → `circuits/` → `charging/` → "
        "`protection/` → `system_models/` → `validation/` → `hardening/` → `scripts/`。\n"
        "- 详见 `portfolio/三项目源码学习路线.md`。\n\n"
        "## 5. 环境复现说明\n\n"
        "```powershell\n"
        "conda run --no-capture-output -n kaifa_battery python -B -m <module>\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\battery_final_acceptance.ps1\n"
        "```\n\n"
        "- 脚本通过 `$PSScriptRoot` 自定位，可从任意工作目录调用。\n"
        "- KiCad 未安装：EDA 相关交付全部 BLOCKED。\n\n"
        "## 6. 验收状态\n\n"
        "- 软件与仿真：COMPLETE_WITH_OPEN_ITEMS（PI 5× 分离、低 SOC、LC 谐振为保留 FAIL）。\n"
        "- EDA 硬件：BLOCKED（KiCad 未安装，无原理图/PCB/ERC/DRC）。\n"
        "- 硬件验证：未进行（无打样、无实测）。\n"
    )


def build_project_handbook(run_id: str) -> str:
    return (
        "# BatteryLab 项目学习与面试实战手册\n\n"
        f"> 对应最终源码与真实运行结果；生成运行 `{run_id}`。全部为软件仿真与公开数据重放。\n\n"
        "## 1. 项目链路\n\n"
        "CALCE INR18650-20R 公开数据 → Rint/一阶/二阶 ECM → 分压-差分-ADC AFE → 背靠背 N-MOSFET 保护 → "
        "被动均衡 → CC-CV 充电 → 3S + Buck 系统联合仿真 → TestLab 接口判定。\n\n"
        "## 2. 关键真实数值\n\n"
        "| 指标 | 数值 | 来源 |\n|---|---|---|\n"
        "| AFE 电压/电流最坏情况（基线） | 30.887 mV / 37.736 mA | 解析误差预算 |\n"
        "| AFE 候选 D | 3.837 mV / 6.666 mA | 解析误差预算 + SPICE 角点 |\n"
        "| 蒙特卡洛校准后 RMSE | 0.8730 mV / 0.8396 mA | 1000 组数学采样 |\n"
        "| 故障→电流抑制 | 0.871 µs | 真实 MOSFET ngspice |\n"
        "| 串联导通电阻 | 30.67 mΩ | 真实 ngspice 工作点 |\n"
        "| 软启动启动能量 | 0.2492 → 0.1368 J | 开关级 ngspice |\n"
        "| 抗饱和 CV 过冲 | 3.257 → 2.068 mV | 开关级 ngspice |\n"
        "| 低 SOC 0–5% RMSE | 157.7 mV（最大 358.2 mV） | CALCE 公开数据重放 |\n"
        "| 系统效率 | 94.158 → 95.206% | 联合仿真 |\n"
        "| 系统纹波 | 24.54 → 21.00 mV | 联合仿真 |\n\n"
        "## 3. 源码索引\n\n"
        "- `hardening/common.py`：时间平均、能量、对照与 Run 目录。\n"
        "- `hardening/afe_worst_case.py`：误差贡献与预算；`hardening/afe_optimization.py`：候选与蒙特卡洛。\n"
        "- `hardening/protection_physical_validation.py`：真实 MOSFET 网表与事件提取。\n"
        "- `hardening/charging_control_comparison.py`：软启动、PI 网格、抗饱和。\n"
        "- `hardening/low_soc_model_analysis.py`：分区误差与模型对照。\n"
        "- `hardening/system_candidate_validation.py`：LC 与控制器候选复验。\n"
        "- `hardening/domain_audit.py`：有效域、SOH、LLC 分类。\n"
        "- `hardening/eda_status.py`：KiCad 与交付物状态。\n\n"
        "## 4. 复现\n\n"
        "```powershell\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\battery_final_acceptance.ps1\n"
        "```\n\n"
        "## 5. 60 道独立实操练习\n\n"
        + "\n".join(
            f"{index}. **[{theme}]** {question}"
            for index, (theme, question, _hint) in enumerate(EXERCISE_THEMES, start=1)
        )
        + "\n\n（参考答案见 `portfolio/独立实操练习参考答案.md`）\n\n"
        "## 6. 200 道综合面试题\n\n"
        "（完整题目与要点见 `portfolio/综合面试题库与参考答案.md`，按 20 个主题分组。）\n\n"
        "## 7. 90 天学习计划\n\n"
        "| 周次 | 主题 | 交付物 |\n|---|---|---|\n"
        + "\n".join(f"| {week} | {theme} | {deliverable} |" for week, theme, deliverable in PLAN)
        + "\n\n## 8. 真实性边界\n\n"
        "- 公开数据不是本人采集；SPICE 不是硬件实测；ERC/DRC 不等于硬件验证；测试数量不是电气性能。\n"
        "- 失败项永久保留：AFE 基线、PI 5× 分离、低 SOC、LC 谐振。\n"
    )


def build_exercise_answers() -> str:
    lines = ["# 60 道独立实操练习参考答案", "", "每题给出要点；数值均来自本项目真实运行。", ""]
    for index, (theme, question, hint) in enumerate(EXERCISE_THEMES, start=1):
        lines.append(f"{index}. **[{theme}]** {question}\n   - 参考要点：{hint}")
    return "\n".join(lines) + "\n"


def build_interview_book() -> str:
    lines = ["# 综合面试题库与参考答案（200 题）", "", "按 20 个主题分组，每题附回答要点。", ""]
    count = 0
    for theme, items in INTERVIEW.items():
        lines.append(f"## {theme}")
        for question, answer in items:
            count += 1
            lines.append(f"{count}. {question}\n   - {answer}")
        lines.append("")
    if count != 200:
        raise RuntimeError(f"面试题数量应为 200，实际 {count}")
    return "\n".join(lines)


def build_plan_book() -> str:
    lines = ["# 90 天研发能力提升计划", "", "| 周次 | 主题 | 交付物 |", "|---|---|---|"]
    for week, theme, deliverable in PLAN:
        lines.append(f"| {week} | {theme} | {deliverable} |")
    lines += [
        "", "## 每周节奏", "",
        "- 周一至周三：读文档 + 复现实验；周四：写分析；周五：复盘并记录失败项。",
        "- 每两周一次口头答辩，用真实数值回答，不看稿。",
        "", "## 验收标准", "",
        "- 能独立复现 AFE 预算、保护时序、软启动与系统闭环四类实验；",
        "- 能解释每个失败项的原因，而不是只报成功项。", "",
    ]
    return "\n".join(lines)


def build_upload_order() -> str:
    return (
        "# 学习资料上传顺序\n\n"
        "## 1. 先看结论\n\n"
        "1. `portfolio/BatteryLab_最终简历量化成果.md`\n"
        "2. `portfolio/BatteryLab_研发能力补强报告.md`\n"
        "3. `portfolio/BatteryLab_工程指标真实性核查报告_v2.md`\n\n"
        "## 2. 再看证据\n\n"
        "4. `portfolio/BatteryLab_AFE精度优化前后对照.md`\n"
        "5. `portfolio/BatteryLab_MOSFET保护真实性复验.md`\n"
        "6. `portfolio/BatteryLab_CC_CV控制优化前后对照.md`\n"
        "7. `portfolio/BatteryLab_电池模型及系统复核报告.md`\n"
        "8. `portfolio/BatteryLab_KiCad硬件设计交付报告.md`\n"
        "9. `portfolio/stage9_engineering_evidence.md`\n\n"
        "## 3. 再看学习材料\n\n"
        "10. `docs/stage10/00_learning_manual.md`\n"
        "11. `portfolio/BatteryLab_项目学习与面试实战手册.md`\n"
        "12. `portfolio/独立实操练习手册.md` → `portfolio/独立实操练习参考答案.md`\n"
        "13. `portfolio/综合面试题库与参考答案.md`\n"
        "14. `portfolio/90天研发能力提升计划.md`\n\n"
        "## 4. 最后看跨项目\n\n"
        "15. `portfolio/三项目真实量化成果总表.md`\n"
        "16. `portfolio/三项目综合研发技术学习手册.md`\n"
        "17. `portfolio/电子电路与PCB设计学习手册.md`\n"
        "18. `portfolio/三项目源码学习路线.md`\n"
    )


def build_three_project_table() -> str:
    testlab_path = ROOT / "portfolio" / "resume_metrics.csv"
    if testlab_path.is_file():
        import pandas as pd

        frame = pd.read_csv(testlab_path, encoding="utf-8-sig", dtype=str).fillna("")
        total = len(frame)
        verified = int(frame["verification_status"].str.startswith("VERIFIED").sum())
        resume = int((frame["resume_suitable"] == "Y").sum())
        testlab_line = f"{total} 项指标，{verified} 项 VERIFIED，{resume} 项可写简历"
    else:
        testlab_line = "未找到 portfolio/resume_metrics.csv"
    return (
        "# 三项目真实量化成果总表\n\n"
        "> 三个项目均为软件仿真/公开数据重放/自动化测试；无硬件实测。跨项目数字各自引用原证据文件。\n\n"
        "| 项目 | 定位 | 代表指标 | 数值 | 验证状态 | 证据 |\n|---|---|---|---|---|---|\n"
        f"| TestLab | 虚拟仪器与自动化测试台 | 量化指标 / 用例 | {testlab_line}；3 类虚拟仪器、12 用例、4 方案、35 检查项 | VERIFIED（软件测试） | `portfolio/resume_metrics.csv`、`TestLab/portfolio/` |\n"
        "| PowerLab | Buck 功率级与控制 | 标称系统效率 / 纹波 | 93.2917% / 19.3483 mVpp；候选 68 µH/330 µF：纹波 10.5901 mV（−45.82%）、效率 94.8904%（+1.4648 pp） | VERIFIED（SPICE） | `portfolio/PowerLab_最终简历量化成果.md` |\n"
        "| BatteryLab | 3S 电池采样-保护-充电-系统 | AFE 预算 / 保护 / 系统 | 30.887→3.837 mV；37.736→6.666 mA；故障→抑制 0.871 µs；系统效率 94.158→95.206% | VERIFIED（仿真） | `BatteryLab/portfolio/BatteryLab_真实量化工程成果总表_v2.md` |\n\n"
        "## 说明\n\n"
        "- TestLab 的 VERIFIED 指软件行为与接口验证，不代表电气性能。\n"
        "- PowerLab 的效率为 SPICE 积分口径，不是硬件测量。\n"
        "- BatteryLab 的 EDA/PCB 为 BLOCKED，未计入任何“已完成硬件”成果。\n"
    )


def build_three_project_manual() -> str:
    return (
        "# 三项目综合研发技术学习手册\n\n"
        "## 1. 三个项目解决的问题\n\n"
        "| 项目 | 问题 | 关键方法 |\n|---|---|---|\n"
        "| TestLab | 仪器驱动与自动化测试是否可靠 | 虚拟仪器 + SCPI + 用例编排 + 回归 |\n"
        "| PowerLab | Buck 功率级与控制能否达标 | 非理想 SPICE + 参数扫描 + PI 整定 |\n"
        "| BatteryLab | 3S 电池链路能否闭环 | ECM + AFE 误差预算 + 真实 MOSFET 保护 + 联合仿真 |\n\n"
        "## 2. 共享技术栈\n\n"
        "- Python + NumPy/SciPy + pandas；Conda 环境隔离；pytest 回归。\n"
        "- 真实 ngspice（经 PySpice 或网表）求解，不伪造波形。\n"
        "- 统一 Run 目录与证据 JSON，禁止覆盖历史。\n\n"
        "## 3. 能力矩阵\n\n"
        "| 能力 | TestLab | PowerLab | BatteryLab |\n"
        "|---|---|---|---|\n"
        "| 仪器/接口 | 强 | 中 | 中（TestLab 接口判定） |\n"
        "| 功率级建模 | 弱 | 强 | 中（Buck 平均/开关级） |\n"
        "| 电池建模 | 无 | 无 | 强（Rint/一阶/二阶） |\n"
        "| 模拟采集 | 中 | 弱 | 强（误差预算+校准） |\n"
        "| 控制 | 弱 | 强 | 中（CC-CV + 系统 PI） |\n"
        "| EDA/PCB | 无 | 无 | BLOCKED |\n"
        "| 测试与回归 | 强 | 强 | 强 |\n\n"
        "## 4. 真实性准则（三项目统一）\n\n"
        "- 公开数据、仿真值、配置值、实测值四类必须分开标注。\n"
        "- 失败与未达标项保留，不用改限值制造改善。\n"
        "- 测试通过数不是性能指标；ERC/DRC 不是硬件验证。\n\n"
        "## 5. 建议学习顺序\n\n"
        "1. TestLab：先理解仪器抽象与用例编排。\n"
        "2. PowerLab：再理解功率级损耗与闭环整定。\n"
        "3. BatteryLab：最后把电池模型、采集、保护、充电与系统串起来。\n"
    )


def build_pcb_manual() -> str:
    return (
        "# 电子电路与 PCB 设计学习手册\n\n"
        "> 结合本项目真实设计输入；BatteryLab 的 KiCad/PCB 为 BLOCKED，本手册不虚构已完成设计。\n\n"
        "## 1. 模拟采集\n\n"
        "- 分压 + 差分放大 + ADC：共模电压 9.7 V 会放大电阻失配误差，比例匹配比单个精度更重要。\n"
        "- 输入折算误差 = 输出误差 / 增益；最坏情况用线性叠加，RSS 只作辅助。\n"
        "- 分流电阻：阻值、功率降额、TCR、开尔文连接；本项目 10 mΩ、0.5 W、62.5 mW 实际耗散。\n"
        "- 两点校准消除增益与零点，但不能消除量化与噪声。\n\n"
        "## 2. 保护与功率器件\n\n"
        "- 背靠背 N-MOSFET 共源可双向阻断；体二极管方向决定阻断能力。\n"
        "- Rds(on) 与并联数决定导通损耗；栅极电荷与驱动电阻决定关断速度。\n"
        "- 过流保护链：采样 → 比较/峰值保持 → 回差 → RC 确认 → 栅极驱动。\n"
        "- 关断应力：Vds 过冲、峰值电流与关断能量要一起看。\n\n"
        "## 3. Buck 与无源器件\n\n"
        "- 占空比 Vout=D·Vin；电感纹波 ΔI=Vin·D·(1−D)/(L·f)；输出纹波含容性与 ESR 分量。\n"
        "- LC 谐振 1/(2π√LC)：本项目 11.07 kHz，低于 12–17 kHz 目标（FAIL 保留）。\n"
        "- 效率必须用能量比；平均电压乘平均电流会高估。\n\n"
        "## 4. PCB 设计要点\n\n"
        "- 叠层与地平面：功率回路最小化，采样走线远离开关节点。\n"
        "- 开尔文采样、差分对等长、模拟地与功率地单点连接。\n"
        "- 降额：电压/电流/温度；均衡电阻 200.6 mW / 250 mW（1206）。\n"
        "- ERC 查电气规则，DRC 查间距线宽；两者都不等于硬件验证。\n\n"
        "## 5. 本项目实际状态\n\n"
        "- 已完成：引脚映射（BMS 33 行、充电器 25 行）、BOM 完整性、降额与理论功耗计算。\n"
        "- 未完成：原理图、PCB、ERC、DRC、Gerber、钻孔、STEP（KiCad 未安装，BLOCKED）。\n"
        "- 学习建议：先用 KiCad 画最小 Buck + 采样电路，跑通 ERC/DRC，再扩展 BMS。\n"
    )


def build_source_route() -> str:
    return (
        "# 三项目源码学习路线\n\n"
        "## 1. TestLab（虚拟仪器与测试台）\n\n"
        "1. `instruments/`：仪器抽象与 VISA 资源。\n"
        "2. `engine/`、`core/`：执行引擎与用例模型。\n"
        "3. `bench/`、`analysis/`：测试方案与判定。\n"
        "4. `ui/`、`scripts/`：入口与回归。\n\n"
        "## 2. PowerLab（Buck 功率级与控制）\n\n"
        "1. `circuits/`：非理想 Buck 网表。\n"
        "2. `simulations/`、`experiments/`：扫描与实验编排。\n"
        "3. `control/`：PI 与环路分析。\n"
        "4. `analysis/`：损耗分解与判定。\n"
        "5. `validation/`、`scripts/`：复验与硬化脚本。\n\n"
        "## 3. BatteryLab（3S 电池链路）\n\n"
        "1. `analysis/`：误差预算与通用分析。\n"
        "2. `battery_models/`、`identification/`：ECM 与参数辨识。\n"
        "3. `circuits/`：电池、AFE、保护、充电网表。\n"
        "4. `sensing/`、`estimation/`：采集与 SOC/SOH。\n"
        "5. `charging/`、`protection/`：CC-CV 与保护逻辑。\n"
        "6. `system_models/`、`simulations/`：系统联合仿真。\n"
        "7. `validation/`、`integration/`：接口判定。\n"
        "8. `hardening/`、`scripts/`：本轮补强与验收。\n\n"
        "## 4. 阅读原则\n\n"
        "- 先读结果 JSON 与文档，确认数字从哪来，再读实现。\n"
        "- 每个模块都要能回答：输入是什么、输出是什么、失败时保留了什么。\n"
        "- 不修改 TestLab/PowerLab；跨项目复算使用独立工作副本。\n"
    )


def build_delivery_zip() -> str:
    import zipfile
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = PROJECT / "deliverables"
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = target_dir / f"BatteryLab_v2_delivery_{stamp}.zip"
    files: list[Path] = []
    files += sorted(PORTFOLIO.glob("BatteryLab_*.md"))
    files += sorted(PORTFOLIO.glob("BatteryLab_*.csv"))
    files += sorted(PORTFOLIO.glob("stage9_engineering_evidence.md"))
    files += sorted(PORTFOLIO.glob("system_*.md")) + sorted(PORTFOLIO.glob("system_*.csv"))
    files += sorted((PROJECT / "docs").glob("10*.md")) + sorted((PROJECT / "docs").glob("113_*.md"))
    files += sorted(DOCS.glob("*.md"))
    files.append(PROJECT / "configs" / "hardening_config.yaml")
    files += sorted((PROJECT / "hardening").glob("*.py"))
    files += sorted((PROJECT / "scripts").glob("hardening_*.py"))
    for name in ("battery_stage10_demo.py", "battery_final_acceptance.ps1", "audit_resume_metrics.py"):
        files.append(PROJECT / "scripts" / name)
    files += sorted((PROJECT / "tests").glob("test_hardening*.py"))
    for name in (
        "test_afe_worst_case.py",
        "test_afe_optimization.py",
        "test_protection_event_extraction.py",
        "test_protection_physical_validation.py",
        "test_charging_control_comparison.py",
        "test_low_soc_validation.py",
        "test_system_candidate_validation.py",
    ):
        files.append(PROJECT / "tests" / name)
    for area in ("afe", "protection", "charging", "ecm", "system", "domain", "eda", "baseline"):
        runs = sorted((PROJECT / "results" / "hardening" / area).glob("run_*"))
        if not runs:
            continue
        for path in runs[-1].iterdir():
            if path.is_file() and path.suffix in {".json", ".md", ".csv", ".cir"}:
                files.append(path)
    acceptance = _latest_acceptance()
    if acceptance is not None:
        files.append(acceptance)
        files.append(acceptance.with_name("acceptance.md"))
    written = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            if not path.is_file():
                continue
            bundle.write(path, arcname=str(path.relative_to(PROJECT)))
            written += 1
    return f"{archive} ({written} files)"


def main() -> int:
    run = new_run("stage10")
    DOCS.mkdir(parents=True, exist_ok=True)
    files = {
        "00_learning_manual.md": build_manual(),
        "01_exercises_60.md": build_exercises(),
        "02_interview_200.md": build_interview(),
        "03_90_day_plan.md": build_plan(),
    }
    written = []
    for name, text in files.items():
        path = DOCS / name
        path.write_text(text, encoding="utf-8")
        written.append(str(path))

    extra = {
        PROJECT / "docs" / "113_stage10_validation.md": build_validation_doc(run.name),
        PORTFOLIO / "BatteryLab_项目学习与面试实战手册.md": build_project_handbook(run.name),
        PORTFOLIO / "独立实操练习手册.md": build_exercises(),
        PORTFOLIO / "独立实操练习参考答案.md": build_exercise_answers(),
        PORTFOLIO / "综合面试题库与参考答案.md": build_interview_book(),
        PORTFOLIO / "90天研发能力提升计划.md": build_plan_book(),
        PORTFOLIO / "学习资料上传顺序.md": build_upload_order(),
        ROOT_PORTFOLIO / "三项目真实量化成果总表.md": build_three_project_table(),
        ROOT_PORTFOLIO / "三项目综合研发技术学习手册.md": build_three_project_manual(),
        ROOT_PORTFOLIO / "电子电路与PCB设计学习手册.md": build_pcb_manual(),
        ROOT_PORTFOLIO / "三项目源码学习路线.md": build_source_route(),
    }
    for path, text in extra.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(str(path))

    archive = build_delivery_zip()
    written.append(archive)

    checks = [{"path": rel, "exists": (PROJECT / rel).is_file()} for rel in REQUIRED]
    root_checks = [{"path": rel, "exists": (ROOT / rel).is_file()} for rel in ROOT_REQUIRED]
    missing = [item["path"] for item in checks if not item["exists"]]
    missing += [item["path"] for item in root_checks if not item["exists"]]
    acceptance = {
        "run_id": run.name,
        "status": "PARTIAL_COMPLETION",
        "reason": "学习/面试材料已生成；EDA 仍 BLOCKED（KiCad 未安装），硬件未验证。",
        "written": written,
        "required_artifacts": checks + root_checks,
        "missing": missing,
        "exercise_count": len(EXERCISE_THEMES),
        "interview_count": sum(len(items) for items in INTERVIEW.values()),
        "delivery_archive": archive,
        "hardware_validated": False,
        "note": "第十阶段不改变任何历史结果，不声称硬件验证。",
    }
    write_json(run / "stage10_acceptance.json", acceptance)
    print(json.dumps({
        "run_id": run.name,
        "written_count": len(written),
        "missing": missing,
        "exercise_count": acceptance["exercise_count"],
        "interview_count": acceptance["interview_count"],
        "delivery_archive": archive,
        "status": acceptance["status"],
    }, ensure_ascii=False))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())

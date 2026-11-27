# 68 第九阶段验证报告

报告时间：2026-11-25（Asia/Shanghai）
阶段范围：Streamlit 电源仿真可视化平台与统一工程分析工作台
结论：**Web 平台可运行，8 个页面可渲染，6 类任务均通过真实 ngspice 执行完成；
取消/超时的“真实长任务”演练、硬件对照与部分视觉验收仍未验证。**

## 1. 实际环境

| 项目 | 实际值 |
| --- | --- |
| Python | 3.11.18（`C:\\Users\\<user>\.conda\envs\kaifa_power\python.exe`） |
| PySpice | 1.5 |
| ngspice | ngspice-34 共享 DLL（进程内求解） |
| Streamlit | 1.67.0 |
| Plotly | 7.2.0 |
| pandas | 3.0.6 |
| NumPy | 1.26.4 |
| SciPy | 1.17.1 |
| pyarrow | 17.0.0（为兼容 NumPy 1.26 从 26.0.1 降级） |
| 操作系统 | Windows-10-10.0.26200-SP0 |

## 2. 验证命令与真实结果

| 命令 | 结果 |
| --- | --- |
| `conda run -n kaifa_power python -m pytest tests -q` | **854 passed**，47.96 s |
| `conda run -n kaifa_power python -m scripts.verify_web` | **PASS (18/18)**，结果写入 `results/stage9/web_verification.json` |
| `conda run -n kaifa_power python -m scripts.web_smoke_demo --model voltage_divider` | COMPLETED，Job `job_20261125_175754_7c9cfecb` |
| `conda run -n kaifa_power python -m scripts.web_smoke_demo --model nonideal_buck --end-ms 1` | COMPLETED，Job `job_20261125_175819_acecc749` |
| `GET /_stcore/health` | `200 ok`（18:06:29，`results/stage9/web_health.json`） |
| 浏览器打开 `http://127.0.0.1:8502` | PASS（修复 pyarrow 后无异常文本） |

第九阶段开始前基线：659 passed。本阶段新增 195 个测试，全部通过。

## 3. 真实任务集成结果

| 任务类型 | Job ID | 结果 | 主要 Run |
| --- | --- | --- | --- |
| 电路仿真（分压） | `job_20261125_175754_7c9cfecb` | COMPLETED | `20261125_175758_a3c13f6a` |
| 电路仿真（非理想 Buck） | `job_20261125_175819_acecc749` | COMPLETED | `20261125_175823_618448b9` |
| 参数扫描（L=22/47 µH） | `job_20261125_180902_3c0c292e` | COMPLETED | `20261125_180908_67bda4de` |
| 数值验证（200/100 ns） | `job_20261125_180908_b377b668` | COMPLETED | `20261125_180912_f03534f4` 等 3 个 |
| Monte Carlo（5 样本） | `job_20261125_180922_7ac3b245` | COMPLETED | `20261125_180931_e7524ace` |
| 闭环控制（2 ms） | `job_20261125_180946_fcad3ab2` | COMPLETED | `20261125_180950_f6730ae6` |
| 性能分析（派生） | `job_20261125_181000_21ea3429` | COMPLETED | `20261125_181005_4c4e7b8a` |

所有任务均由 `JobManager.submit()` 创建独立工作进程执行，未使用 Mock 求解。

## 4. 运行索引

`conda run -n kaifa_power python -m scripts.rebuild_run_index` 实际输出：

- 313 条记录，313 个唯一 `run_id`（无去重丢失）；
- `spice_simulation` 312 条，`spice_derived` 1 条；
- 类型：simulation 309、parameter_sweep 1、numerical_validation 1、monte_carlo 1、derived_analysis 1；
- 其中 118 条早期历史元数据没有 `status` 字段，索引如实记为 `unknown`。

## 5. 导出与报告证据

| 产物 | 文件 | 大小 |
| --- | --- | --- |
| HTML 报告 | `results/stage9/run_20261125_175823_618448b9_report.html` | 14,764 B |
| 指标 CSV | `results/stage9/run_20261125_175823_618448b9_metrics.csv` | 4,637 B |
| 摘要 JSON | `results/stage9/run_20261125_175823_618448b9_summary.json` | 3,074 B |
| 完整波形 CSV | `results/stage9/run_20261125_175823_618448b9_waveform.csv` | 3,680,392 B |

HTML 报告由 `ui/export_service.html_report()` 从磁盘真实数据生成，未重新运行 SPICE。

## 6. 浏览器验证

1. 首次验证发现真实缺陷：`pyarrow 26.0.1` 要求 NumPy ≥2，而 PySpice 环境固定 NumPy 1.26.4，
   导致 `st.dataframe` 渲染表格时报 `ImportError`，页面异常边界显示“页面渲染出现异常”。
2. 处理：将 `pyarrow` 固定为 `17.0.0`，重启服务。
3. 复验：仪表盘、环境证据、结果概况、最近运行、任务状态、侧边栏导航均正常，无异常文本。
4. 截图：`results/stage9/screenshots/powerlab_dashboard_refreshed.jpg`、
   `results/stage9/screenshots/powerlab_final.jpg`。

未做多浏览器、移动端与全部 8 页的逐页截图；其余页面由 AppTest 验证渲染无异常。

## 7. 最终开发汇报（50 项）

1. **新增/修改文件**：新增 `jobs/` 9 个模块、`storage/run_index.py`、`storage/result_repository.py`、
   `ui/` 14 个模块与 8 个视图、`app.py`、`.streamlit/config.toml`、`configs/web_config.yaml`、
   `configs/job_limits.yaml`、3 个脚本、14 个测试文件、8 份文档；未修改前八阶段业务模块。
2. **前八阶段真实复用模块**：`simulations.*`、`circuits.*`、`control.models`、`analysis.*`、
   `validation.*`、`storage.result_store`。
3. Python：3.11.18。
4. PySpice：1.5。
5. ngspice：34（共享 DLL）。
6. Streamlit：1.67.0。
7. Plotly：7.2.0。
8. Web 页面：8 个。
9. 页面功能：总览、电路仿真、性能分析、闭环控制、批量实验（扫描/MC/数值验证）、
   数值验证与验收、历史记录、关于与限制。
10. 业务服务接口：`ui/service.py` 共 23 个公开函数。
11. 仿真模型：6 个（分压、RC、RL、RLC、近理想 Buck、非理想 Buck）。
12. 任务类型：6 个。
13. 执行方式：`sys.executable -m jobs.worker` 独立子进程，状态落盘。
14. 并发控制：`JobManager` 锁 + 活跃任务扫描，默认并发 1。
15. 进度定义：计划/完成/失败工况、SPICE 调用、缓存命中；无真实计数时不显示比例。
16. 取消验证：单元级 11 项通过；真实长求解中途取消 **NOT_VERIFIED**。
17. 超时验证：核对逻辑单元级通过；真实 3600 s 超时 **NOT_VERIFIED**。
18. 重复提交：相同 SI 指纹被 `DuplicateJobError` 拒绝，测试通过。
19. 资源预算：并发 1、单任务 3600 s、工况 300 s、SPICE 120、MC 30、绘图 30,000、
   磁盘 1024 MB、日志 2 MB。
20. 表单：6 个模型表单 + 扫描 + 闭环 + Monte Carlo + 数值验证，共 10 个表单面；
    服务端再次校验并统一转 SI。
21. 图表：波形、双面板、扫描曲线、直方图、箱线图、收敛曲线，共 6 类。
22. 原始波形规模：非理想 Buck 运行 14,761 点。
23. 展示点数：默认 8,000，可选 2,000–30,000，配置上限 30,000。
24. 峰值保留：`test_downsample_keeps_extreme_points` 通过（300→≤100 点，峰值 10.0 保留）。
25. 波形读取耗时：完整 0.032 s；30,000 点上限 0.036 s。
26. 历史记录：索引 313 条。
27. 索引去重：313 条记录 / 313 个唯一 Run ID。
28. CSV 导出：指标 4,637 B；完整波形 3,680,392 B。
29. JSON 导出：摘要 3,074 B，合法 JSON。
30. HTML 报告：14,764 B，自包含，含真实指标与“不是硬件实测”声明。
31. 电路仿真 Web 集成：2 个真实任务 COMPLETED。
32. 参数扫描 Web 集成：真实 COMPLETED，汇总表落盘。
33. 闭环控制 Web 集成：真实 COMPLETED（2 ms，变体 E）。
34. 可信度验证 Web 集成：数值验证真实 COMPLETED（200/100 ns）。
35. AppTest：11 个测试。
36. 八页加载：全部无异常。
37. Pytest 总数：854。
38. 通过/失败：854 通过 / 0 失败。
39. 覆盖率：本阶段未执行覆盖率统计。
40. 真实 SPICE 集成测试：6 类任务、7 个 Job（含派生分析）全部 COMPLETED。
41. 启动命令：`conda run -n kaifa_power python -m streamlit run app.py --server.port 8502`。
42. HTTP 健康检查：`200 ok`。
43. 浏览器验证：PASS（修复 pyarrow 后），仅桌面单浏览器。
44. 截图路径：`results/stage9/screenshots/` 下 2 张。
45. 本阶段贡献：新增 Web 编排层、8 页工作台、任务生命周期、结果索引、导出与 195 个测试。
46. 可量化成果：8 页面、6 任务类型、6 模型、23 服务接口、6 图表、313 索引运行、854 测试。
47. 尚未实现：Bode/零极点页、负载瞬态专用视图、账号体系、硬件测量接入、截图自动化。
48. 已知问题：`use_container_width` 弃用警告；pyarrow 需固定 17.x；118 条历史运行状态为 unknown；
    索引需手动重建才能包含最新运行；单用户、单并发。
49. 未验证事项：真实求解中取消、真实 3600 s 超时、运行中重启 Web、extended profile、
    硬件对照、多浏览器/响应式视觉验收。
50. **二十五道面试题**：
    1. 为什么把 SPICE 求解放进独立子进程，而不是 Streamlit 线程？
    2. `job.json` 作为唯一状态事实源有哪些优缺点？
    3. 如何保证任务状态文件的原子写与并发安全？
    4. 任务状态机中 `CANCEL_REQUESTED` 与 `CANCELLED` 为什么要分开？
    5. ngspice 以 DLL 进程内运行时，如何终止一次求解？
    6. 如何设计两级取消机制？各自的局限是什么？
    7. 为什么要做“惰性核对”而不是后台心跳线程？
    8. 如何防止死进程任务永久停留在 RUNNING？
    9. 任务超时与工况超时的区别是什么？
    10. 如何用请求指纹防止重复提交？指纹应包含哪些字段？
    11. 单并发限制对用户体验和资源安全各有什么影响？
    12. 为什么表单使用工程单位、提交时统一转 SI？
    13. 如何避免单位转换在表单、请求、worker 之间重复或遗漏？
    14. 为什么 handler 使用静态白名单映射而不是动态导入？
    15. 如何防止任务 ID 或运行 ID 造成路径穿越？
    16. 结果索引为什么只存元数据？如何保证可重建？
    17. 索引版本升级时如何处理旧索引？
    18. Run ID 与 Job ID 的区别？一对多关系如何表达？
    19. 派生分析如何证明自己没有重新运行 SPICE？
    20. 为什么展示波形必须抽样，而分析必须使用原始波形？
    21. 等间隔抽样为什么会漏掉峰值？最小/最大值降采样如何改进？
    22. 抽样后仍可能丢失极值，工程上如何兜底？
    23. CSV/JSON/HTML 导出如何做到“不触发重新仿真”？
    24. AppTest 能证明什么、不能证明什么？
    25. 如何向评审说明“仿真 PASS”与“硬件实测通过”的区别？

## 8. 手工验收要点

详细步骤见 [65_web_user_guide.md](65_web_user_guide.md)。最小验收路径：

1. 启动平台，确认总览加载 313 条历史运行；
2. 电路仿真提交非理想 Buck，观察工况进度与 SPICE 调用次数；
3. 历史记录重建索引，打开 `20261125_175823_618448b9`，查看波形与指标；
4. 导出 HTML 报告，确认包含运行编号、任务编号与 simulation 声明；
5. 批量实验分别提交扫描、MC、数值验证；
6. 闭环控制提交 2 ms 工况；
7. 重复点击提交，确认被拒绝；
8. 提交后立即取消，记录是否在安全点退出（当前未验证长任务中途取消）。

## 9. 结论

- 前八阶段 659 个测试保持通过，新增 195 个测试全部通过；
- 6 类任务均通过真实 ngspice 执行，Web 层未伪造结果；
- 8 个页面可渲染，HTTP 健康检查与桌面浏览器验证通过；
- 历史索引、导出与 HTML 报告均来自真实文件；
- 取消/超时的真实长任务演练、硬件对照和完整视觉验收仍需人工完成。

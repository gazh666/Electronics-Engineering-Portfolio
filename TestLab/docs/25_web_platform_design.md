# 25 Web 平台设计（第九阶段）

## 1. 目标

在现有 PyVISA-sim + VirtualDUT 后端之上，提供一个可实际操作六类功能的
Streamlit 工业测试平台。要求：

- 复用既有业务模块，不重新实现 DUT 公式、限值判定或 SCPI 拼接；
- 所有测试结果由真实后端执行产生，禁止硬编码 PASS；
- 按钮必须连接真实服务，不能只有界面；
- 所有模拟数据标注来源；
- 不开发第十阶段的综合报告系统、Docker、Linux 部署或 PowerLab。

## 2. 分层

```text
app.py                       页面入口、侧边导航
ui/views/                    六个页面（只负责展示与输入）
ui/service.py                唯一服务层：调用后端、串行任务锁、导出
ui/state.py                  session_state 默认值与结果缓存
ui/theme.py                  颜色、状态映射、CSS、Plotly 主题
ui/formatters.py             空值/单位/百分比/时间格式化
ui/components.py             页头、指标卡、表格、事件、导出按钮

engine/ bench/ analysis/ instruments/ models/ reliability/ storage/
```

UI 层不 import pyvisa，不拼接 SCPI，不计算效率或限值。

## 3. 文件结构

```text
TestLab/
├── app.py
├── .streamlit/config.toml
├── ui/
│   ├── __init__.py
│   ├── service.py
│   ├── state.py
│   ├── theme.py
│   ├── formatters.py
│   ├── components.py
│   └── views/
│       ├── __init__.py
│       ├── dashboard.py
│       ├── instruments.py
│       ├── automation.py
│       ├── performance.py
│       ├── reliability.py
│       └── history.py
├── assets/screenshots/
└── tests/
    ├── test_ui_service.py
    ├── test_ui_formatters.py
    ├── test_ui_state.py
    └── test_streamlit_app.py
```

## 4. 服务层接口

`ui.service.TestLabService` 是页面唯一依赖对象。

| 方法 | 作用 |
| --- | --- |
| `get_environment()` | Python/平台/数据模式/数据库路径 |
| `get_dut_summary()` | 读取 `dut_config.yaml` 的模型参数 |
| `get_dashboard_summary()` | 真实 SQLite 统计、最近运行、类别统计、耗时 |
| `discover_instruments()` | 单次会话发现 PS001/DMM001/LOAD001 并识别 |
| `run_instrument_session(...)` | 电源/万用表/负载设置与回读，结束安全关闭 |
| `list_test_cases()` / `list_test_suites()` | 加载并校验 YAML |
| `run_test_suite(...)` | 执行测试方案，真实进度回调 |
| `run_selected_cases(...)` | 执行自定义用例组，停止条件可覆盖 |
| `estimate_sweep_points(...)` | 计算扫描点数，上限 300 |
| `run_performance_sweep(...)` | 负载/线性/二维扫描 |
| `list_fault_scenarios()` | F001–F009 与预设实验预期 |
| `get_retry_policy_summary()` | 当前有限重试配置 |
| `run_fault_scenario(...)` | 单场景可靠性实验 |
| `run_reliability_validation(...)` | 批量可靠性实验 |
| `list_history_runs(...)` | 时间/方案/状态/类型/用例筛选 |
| `get_run_details(...)` | 结果、检查项、故障事件、清理信息 |
| `get_run_artifacts(...)` | 定位运行目录、配置快照、metadata |
| `export_run_csv/json/html(...)` | 内存生成导出内容 |

### 4.1 数据来源

| 场景 | 标签 |
| --- | --- |
| 仪器设定/回读 | `pyvisa-sim SCPI` |
| DUT 模型输出 | `behavioral_model` |
| 故障注入测量视图 | `fault_injected_model` |
| DMM 固定 SCPI 读数 | `static_mock` |

界面不会把 `static_mock` 描述成真实测量，也不会把模型效率写成实测效率。

## 5. 六个页面

### 5.1 运行概览

- 数据来自 SQLite `runs` / `test_results`；
- 状态环形图、PASS/FAIL/ERROR/SKIP 计数、有效通过率、平均耗时；
- 最近 8 次运行、按类别统计、DUT 参数、运行环境；
- 无数据时显示空状态，不生成示例数据。

### 5.2 仪器控制

- 发现按钮启动一次短连接，列出资源与 `*IDN?`；
- 电源：设置电压/限流/输出并回读；
- 万用表：读取固定模拟值，明确标注 `static_mock`；
- 电子负载：模式/拉载电流/输入开关；
- 会话结束关闭负载输入与电源输出并回读确认；
- 页面加载不会自动连接仪器。

### 5.3 自动化测试

- 选择既有方案或自定义用例组；
- 可覆盖 `stop_on_fail` / `stop_on_error`；
- 进度条只在结果持久化后推进；
- 展示运行编号、状态、三种通过率口径、逐用例指标/检查项/质量问题；
- 支持 CSV/JSON/HTML 导出。

### 5.4 性能扫描

- 负载扫描、线性扫描、二维扫描；
- 扫描点上限 300，超限阻止执行；
- 复用 `VirtualTestBench.read_state()` 与 `PerformanceAnalyzer.analyze()`；
- 电压/效率/功率曲线与二维热力图；
- 保护点单独标记，不按稳压限值判 FAIL；
- 空载效率不可定义时显示 N/A；
- 限值来自 `configs/performance_limits.yaml`。

### 5.5 可靠性验证

- 列出 F001–F009、故障类型、目标、操作与预设预期；
- 展示有限重试策略（只读白名单、最大尝试次数、退避）；
- 支持运行单个场景或全部场景；
- 业务 PASS/FAIL/ERROR 与实验 PASS/FAIL 分开显示；
- 展示原始模型 vs 注入视图、故障事件、重试/恢复/耗尽、清理状态；
- F009 展示清理失败后的强制停止与 SKIP；
- 每次运行创建独立注入器与运行目录，结束后释放。

### 5.6 历史记录

- 只读 SQLite；
- 按时间、方案、运行状态、普通/可靠性、运行编号、用例筛选；
- 运行详情含结果、检查项、故障事件、重试/清理、配置快照；
- 导出 CSV/JSON/HTML；
- 不提供“重新执行”按钮。

## 6. 视觉规范

- 主色：工业蓝 `#1d4ed8`；深海军蓝 `#0b1f3a`；背景 `#f5f7fb`；
- 状态色：PASS 绿、FAIL 红、ERROR 橙、SKIP 灰；
- 宽屏布局、白色卡片、统一 Plotly 主题；
- 所有页面顶部显示 SIMULATION 提示。

## 7. 非目标

- 不做用户登录、权限、多租户；
- 不做分布式任务队列；
- 不接真实仪器；
- 不做 Docker/Linux 部署；
- 不开发第十阶段综合报告系统或 PowerLab。

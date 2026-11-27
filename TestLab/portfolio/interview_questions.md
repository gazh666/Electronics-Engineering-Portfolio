# 面试问题准备（55 题）

> 每题包含：简洁回答、深入说明、代码位置、可能的追问、实现范围/边界。
> 回答只描述真实实现；未实现或未验证的内容必须明确说明。

## 一、项目与业务理解（11 题）

### Q1. 这个项目解决什么问题？
- 简洁回答：把“能连仪器读数”提升为可测试、可判定、可追溯、可展示的
  自动化测试平台。
- 深入：覆盖用例/方案管理、四态判定、故障注入、有限重试、历史持久化、
  Web 六页与离线报告；强调工程正确性而非单个读数。
- 代码位置：`engine/`、`ui/service.py`、`reports/generator.py`。
- 追问：和普通脚本区别？答：有判定、失败处理、清理验证、审计记录。
- 范围：模拟环境，无真实硬件。

### Q2. 为什么用 PyVISA-sim？
- 简洁回答：无需真实仪器即可验证 SCPI 通信、超时、异常与完整测试流程。
- 深入：PyVISA-sim 用 YAML 定义仪器响应，可确定性复现只读属性、越界错误、
  无响应超时；真实硬件不可控且成本高。
- 代码位置：`configs/instruments.yaml`、`instruments/`、`docs/03_scpi_protocol.md`。
- 追问：会不会脱离真实？答：驱动层仍走 PyVISA API，替换后端即可接真实仪器，
  但需重新验证量程、超时与校准。
- 范围：所有结果均为仿真。

### Q3. 模拟和真实硬件的边界如何保证不说错？
- 简洁回答：所有记录带来源标签，文档与报告反复声明仿真属性。
- 深入：来源包括 `pyvisa-sim SCPI`、`behavioral_model`、
  `model(virtual_dut)+dmm_noise`、`static_mock`；报告首页有醒目声明；
  验收文档只写“模拟验证”。
- 代码位置：`bench/`、`reports/generator.py`、`README.md`。
- 追问：测试能证明什么？答：证明测试架构与判定流程，不证明芯片性能。
- 范围：`real hardware` 当前不存在。

### Q4. 为什么选 12 V→5 V DC-DC 作为被测对象？
- 简洁回答：工业常见拓扑，输入/输出/效率/保护状态都容易定义且可验证。
- 深入：模型简单但足够覆盖标称、欠压、过压、过流、输入限流、输出关闭；
  便于设计多工况用例与限值。
- 代码位置：`models/virtual_dut.py`、`configs/dut_config.yaml`。
- 追问：模型准确吗？答：是稳态行为模型，不是 SPICE，不含开关细节。
- 范围：预设效率 0.90 不是实测。

### Q5. 项目里的 PASS 代表什么？
- 简洁回答：在模拟条件下，用例的数据质量、DUT 状态与工程限值全部满足。
- 深入：PASS 不等于产品合格，也不等于真实硬件通过；只代表预设验证条件成立。
- 代码位置：`engine/result_judge.py`、`engine/test_runner.py`。
- 追问：FAIL 呢？答：状态不符或指标越限；ERROR 是系统/数据异常。
- 范围：限值来自 `configs/performance_limits.yaml`。

### Q6. 为什么要 PASS/FAIL/ERROR/SKIP 四态？
- 简洁回答：区分“产品不合格”“测试系统故障”“未执行”，避免混为一谈。
- 深入：汇总优先级 `ERROR > FAIL > PASS`；SKIP 不计入有效判定通过率；
  退出码按状态区分，便于 CI。
- 代码位置：`engine/models.py`、`engine/suite_runner.py`。
- 追问：ERROR 和 FAIL 同时存在怎么报？答：整体状态 ERROR 优先。
- 范围：SKIP 必须带原因。

### Q7. SKIP 和 ERROR 的区别？
- 简洁回答：SKIP 是没执行，ERROR 是执行了但无法得到有效结论。
- 深入：强制停止后剩余用例生成 SKIP 并写原因；数据质量异常、清理失败、
  设置值不一致等为 ERROR。
- 代码位置：`engine/suite_runner.py::_skip_result`、`engine/test_runner.py`。
- 追问：SKIP 算通过吗？答：不算，汇总会提示存在未执行用例。
- 范围：不允许静默丢弃。

### Q8. 数据来源标签为什么必要？
- 简洁回答：防止把模型值、固定响应或注入值当成真实测量。
- 深入：报告、数据库、导出都保留来源；DMM 固定读数标 `static_mock`；
  故障注入视图标 `fault_injected_model`，原始 `DUTResult` 不变。
- 代码位置：`bench/virtual_test_bench.py`、`reliability/`。
- 追问：来源会丢吗？答：SQLite 与 JSONL 都持久化 `data_source`。
- 范围：来源不一致会被数据质量检查标记。

### Q9. 0.90 的效率是怎么来的？
- 简洁回答：模型预设参数，不是实验测量值。
- 深入：用于让功率、损耗、效率链路自洽；文档明确不能引用为实测效率。
- 代码位置：`configs/dut_config.yaml`、`docs/09_virtual_dut_model.md`。
- 追问：为什么不是 95%？答：参数可配置，选择不影响架构验证。
- 范围：真实效率需硬件测量。

### Q10. 项目最大的难点是什么？
- 简洁回答：不是通信，而是异常路径与数据一致性。
- 深入：清理失败必须停止、重试只允许只读查询、进度必须在持久化后、
  历史不能被覆盖、报告不能反推历史配置。
- 代码位置：`engine/suite_runner.py`、`reliability/retry_policy.py`、
  `reports/generator.py`。
- 追问：怎么验证？答：针对性测试 + 真实运行 + 发布验收脚本。
- 范围：复合故障覆盖仍有技术债。

### Q11. 如果接真实仪器，需要改什么？
- 简洁回答：替换仪器后端、重新校准与量限校验，补充硬件安全与不确定度。
- 深入：YAML 换成真实资源地址；超时、量程、回读一致性需实测；
  需要急停、互锁、权限与审计；报告来源改为 `real_measurement`。
- 代码位置：`instruments/`、`configs/instruments.yaml`。
- 追问：架构要重写吗？答：不必，桥接与判定层可复用，但必须重新验收。
- 范围：本阶段不接硬件。

## 二、架构与设计（11 题）

### Q12. 分层依赖方向是什么？
- 简洁回答：UI → service → engine/bench/analysis/reliability/storage；
  仪器与模型在底层，禁止反向依赖。
- 深入：`ui/` 不拼 SCPI、不复制公式；`models/` 不 import pyvisa；
  `storage/` 不做业务判定。
- 代码位置：各包 `__init__` 与 `AGENTS.md`。
- 追问：怎么检查？答：代码审查 + 导入检查 + 测试。
- 范围：脚本层允许作为组合根。

### Q13. 为什么 Web 只允许 `ui/service.py` 作为入口？
- 简洁回答：避免页面复制业务逻辑、连接泄漏与并发冲突。
- 深入：页面只收集参数、调用 service、展示结果；service 统一创建/关闭
  资源，统一加锁与进度。
- 代码位置：`ui/service.py`、`ui/views/`。
- 追问：页面能直接查 SQLite 吗？答：不允许，必须走 service。
- 范围：service 不做页面布局。

### Q14. 为什么任务要进程级串行？
- 简洁回答：同一时刻只允许一个任务占用虚拟仪器与数据库写入。
- 深入：模块级 `threading.Lock`，非阻塞获取，已占用立即返回 `TaskBusyError`；
  不声明跨进程/多副本能力。
- 代码位置：`ui/service.py::exclusive_task`。
- 追问：多用户怎么办？答：当前不支持，需要任务队列与多实例隔离。
- 范围：单进程。

### Q15. 为什么仪器对象不能放 `session_state`？
- 简洁回答：序列化、生命周期与并发都不可控，容易泄漏或跨用户共享。
- 深入：每次操作使用短生命周期上下文并在 `finally` 关闭；只缓存结果数据。
- 代码位置：`ui/service.py`、`ui/state.py`。
- 追问：缓存什么？答：汇总、结果、报告路径等纯数据。
- 范围：数据库连接同样禁止缓存。

### Q16. 进度回调为什么必须在持久化之后？
- 简洁回答：否则界面显示完成但数据尚未落盘，刷新后结果丢失。
- 深入：单用例完成并写入 JSONL/SQLite 后才回调；禁止预先填 100%。
- 代码位置：`engine/test_runner.py`、`ui/service.py`。
- 追问：失败怎么办？答：回调失败记录 storage_errors，不伪装成功。
- 范围：进度是真实执行进度。

### Q17. 用例和方案为什么用 YAML？
- 简洁回答：可读、可审查、可版本管理，非程序员也能改参数。
- 深入：未知字段直接报错，防止拼写错误被静默忽略；方案只引用用例编号，
  不复制参数。
- 代码位置：`configs/test_cases.yaml`、`configs/test_suites.yaml`、
  `engine/case_loader.py`。
- 追问：为什么不用数据库？答：测试定义需要代码评审与 diff。
- 范围：旧版字典用例保留但不新增。

### Q18. 为什么未知字段必须报错？
- 简洁回答：配置拼写错误会导致测试“看起来在跑”但参数没生效。
- 深入：例如把 `vin` 写成 `voltage`，静默忽略会用默认值，产生错误结论。
- 代码位置：`engine/case_loader.py`。
- 追问：向后兼容怎么办？答：显式迁移，不做静默兼容。
- 范围：限值键也必须在白名单内。

### Q19. 限值为什么不写在算法里？
- 简洁回答：限值是产品/测试规范，不是算法常量。
- 深入：统一来自 `configs/performance_limits.yaml`，算法只负责计算与比较；
  修改规范无需改代码。
- 代码位置：`analysis/`、`configs/performance_limits.yaml`。
- 追问：不同产品呢？答：替换配置即可，但需重新评审。
- 范围：保护状态用 `NOT_APPLICABLE`。

### Q20. 综合报告为什么只读 SQLite 和快照？
- 简洁回答：报告必须反映当时运行，不能受当前配置或重新执行影响。
- 深入：报告不重跑测试；DUT 参数与限值来自运行目录快照；缺失则显示
  “无法追溯”。
- 代码位置：`reports/generator.py::load_run_bundle`。
- 追问：快照缺失怎么办？答：不拿当前配置冒充历史，明确标记。
- 范围：不合并其他运行数据。

### Q21. 如何避免循环依赖？
- 简洁回答：依赖单向、底层不 import 上层、组合根放在脚本与 service。
- 深入：`reports` 不 import `ui`；`storage` 不 import `engine` 之外的展示层；
  新增 `core.paths` 只被依赖，不反向依赖。
- 代码位置：`core/paths.py`、`verify_release.check_imports`。
- 追问：怎么证明？答：验收脚本导入 12 个核心模块。
- 范围：运行时导入检查，不是静态图分析。

### Q22. 为什么新增 `core/paths.py`？
- 简洁回答：统一本地、Docker、测试三种环境的路径，避免写死与分叉。
- 深入：支持 `TESTLAB_RESULTS_DIR`、兼容 `TESTLAB_RESULTS_ROOT`、
  `TESTLAB_DB_PATH`；默认位置不变；导入不创建目录。
- 代码位置：`core/paths.py`、`app.py`、各存储/脚本。
- 追问：环境变量在导入时读取吗？答：函数在调用时读取，模块常量是快照。
- 范围：Web 用户不能自定义任意路径。

## 三、仪器通信与数据（11 题）

### Q23. 一次 SCPI 读写是怎么走的？
- 简洁回答：页面/脚本 → service/引擎 → 驱动 `write/query` → PyVISA →
  PyVISA-sim → YAML 响应。
- 深入：驱动统一继承 `BaseInstrument`，负责超时、日志、连接状态与幂等关闭；
  业务层不拼 SCPI 字符串。
- 代码位置：`instruments/base.py`、`instruments/power_supply.py`。
- 追问：资源管理谁负责？答：统一 `InstrumentManager`。
- 范围：模拟后端。

### Q24. 为什么设置后要回读？
- 简洁回答：确认仪器真的接受了设置，否则测量结论没有意义。
- 深入：`set_voltage` 后 `get_voltage` 比较，超出容差判 ERROR；
  电子负载的模式与电流同样回读。
- 代码位置：`engine/test_runner.py`。
- 追问：回读不一致算什么？答：ERROR，不继续测量。
- 范围：容差来自配置/常量。

### Q25. 为什么多台虚拟仪器不共享状态？
- 简洁回答：PyVISA-sim 各资源独立，负载拉载不会改变电源回读。
- 深入：如果假设共享，会得到“看似合理但错误”的 DUT 数据；因此必须有
  显式桥接层。
- 代码位置：`engine/dut_bridge.py`、`bench/virtual_test_bench.py`。
- 追问：桥接做了什么？答：读 PSU/ELoad 设置 → 模型 → DMM 噪声。
- 范围：不修改 YAML 响应伪装动态测量。

### Q26. 数据桥接如何保证来源可信？
- 简洁回答：每次读取记录来源，模型结果标 `behavioral_model`，
  噪声读数标 `model(virtual_dut)+dmm_noise`。
- 深入：`BridgeReading.sources` 保存各字段来源；负载关闭按 0 A 计算。
- 代码位置：`engine/dut_bridge.py`。
- 追问：DMM 读数用在哪？答：只做通信链路与静态模拟演示。
- 范围：静态响应标 `static_mock`。

### Q27. DMM 固定响应怎么避免误解？
- 简洁回答：单独方法、单独来源标签，绝不混入业务测量。
- 深入：`get_static_mock_measurements()` 与 `get_model_measurements()`
  明确分开；页面显示来源。
- 代码位置：`bench/virtual_test_bench.py`。
- 追问：报告会用它吗？答：测试业务测量走模型 + 噪声路径。
- 范围：固定响应不代表 DUT 状态。

### Q28. 超时怎么处理？
- 简洁回答：驱动设超时，抛出 `InstrumentTimeoutError`，由分类器判断是否可重试。
- 深入：只有白名单只读查询且分类为 `TRANSIENT_COMMUNICATION` 才重试，
  最大 10 次；写入与断开不重试。
- 代码位置：`instruments/base.py`、`reliability/retry_policy.py`。
- 追问：重试后仍失败？答：按 ERROR 记录，不伪造测量。
- 范围：`KeyboardInterrupt` 不重试但清理。

### Q29. 非法字符串响应怎么处理？
- 简洁回答：解析失败转 `InstrumentError`，数据质量标记，不进入 PASS。
- 深入：NaN/Infinity 进入不一致视图，由数据质量判 ERROR。
- 代码位置：`reliability/error_classifier.py`、`analysis/data_quality.py`。
- 追问：会重试吗？答：非法数据不重试。
- 范围：注入视图不修改原始结果。

### Q30. 设置值越界为什么要提前校验？
- 简洁回答：PyVISA-sim 越界会返回 ERROR 并造成后续响应错位。
- 深入：驱动发送前用 `validate_number` 校验；否则下一次查询会读到上一次错误。
- 代码位置：`instruments/`、`engine/case_loader.py`。
- 追问：这是真实仪器问题吗？答：不同仪器行为不同，但提前校验是通用做法。
- 范围：YAML `e: "ERROR"` 只在越界回包。

### Q31. 为什么保护状态不按稳压限值判 FAIL？
- 简洁回答：保护状态本来就不应稳压，按稳压限值判会误报。
- 深入：状态优先级固定，保护时输出为 0、指标 `NOT_APPLICABLE`，
  只与预期状态比较。
- 代码位置：`models/virtual_dut.py`、`engine/result_judge.py`。
- 追问：预期是保护却正常呢？答：FAIL（状态不符）。
- 范围：数据质量优先于状态判定。

### Q32. 为什么空载效率返回 None？
- 简洁回答：空载输出功率为 0，效率不可定义。
- 深入：返回 0% 或 100% 都会误导；判定为 `N/A`，不参与限值比较。
- 代码位置：`models/virtual_dut.py`、`analysis/metrics.py`。
- 追问：统计怎么办？答：无有效样本输出 `None`，不用 0 代替。
- 范围：文档已说明。

### Q33. 编写仪器 YAML 遇到过什么坑？
- 简洁回答：只读属性必须写 `specs.type`，否则无法按浮点格式输出；
  未定义查询返回 ERROR。
- 深入：越界错误还会导致后续响应错位；无响应查询用于超时测试。
- 代码位置：`configs/instruments.yaml`、`docs/03_scpi_protocol.md`。
- 追问：如何回归？答：驱动测试 + 仪器演示脚本。
- 范围：基于 0.7.1 实测。

## 四、测试、可靠性与存储（12 题）

### Q34. 判定顺序是什么？
- 简洁回答：数据质量 ERROR → DUT 状态 → 工程限值。
- 深入：异常数据不得进入限值判定；状态不符直接 FAIL；全部满足才 PASS。
- 代码位置：`engine/test_runner.py`、`engine/result_judge.py`。
- 追问：空检查项？答：返回 ERROR，禁止默认 PASS。
- 范围：汇总优先级 ERROR > FAIL > PASS。

### Q35. 清理失败怎么处理？
- 简洁回答：该用例标 ERROR，方案强制停止，后续用例 SKIP。
- 深入：清理状态只能 `VERIFIED_OFF / NOT_VERIFIED / NOT_APPLICABLE`；
  不得把未确认改成成功。
- 代码位置：`engine/suite_runner.py`、`engine/test_runner.py`。
- 追问：为什么不继续？答：输出状态未知，继续测试有安全风险。
- 范围：模拟环境同样执行该规则。

### Q36. 重试白名单有哪些？
- 简洁回答：`*IDN? VOLT? CURR? OUTP? INP? MODE?` 等只读查询。
- 深入：仅当异常分类为 `TRANSIENT_COMMUNICATION`；写入、断开、非法数据、
  配置错误、未知异常、清理失败均不重试。
- 代码位置：`configs/retry_policy.yaml`、`reliability/retry_policy.py`。
- 追问：为什么写入不重试？答：可能已生效，重试会造成重复动作。
- 范围：最大 10 次总尝试。

### Q37. 断开故障为什么不自动重连？
- 简洁回答：盲目重连会掩盖问题并可能造成状态不一致。
- 深入：标记会话失效，后续 SCPI 直接失败；由人工或上层策略决定恢复。
- 代码位置：`reliability/`、`instruments/manager.py`。
- 追问：测试怎么结束？答：按 ERROR 记录并清理。
- 范围：不模拟自动重连成功。

### Q38. 恢复率怎么算？
- 简洁回答：可重试故障操作中恢复的比例，按 `operation_id` 去重。
- 深入：分母不是注入次数；业务状态与实验结论分开统计。
- 代码位置：`reliability/reliability_analyzer.py`。
- 追问：为什么去重？答：同一操作多次重试只应算一次恢复机会。
- 范围：统计口径写在文档。

### Q39. 为什么实验预期不能运行后修改？
- 简洁回答：否则会变成“按结果编预期”，失去验证意义。
- 深入：预期固定在 `configs/reliability_experiments.yaml`，运行后只比较。
- 代码位置：`configs/reliability_experiments.yaml`。
- 追问：预期错了怎么办？答：评审后改配置并重新运行，不能改历史结果。
- 范围：实验 10/10 通过。

### Q40. JSONL 和 SQLite 为什么都要写？
- 简洁回答：JSONL 便于逐条追加与人工排查，SQLite 便于筛选与统计。
- 深入：两者都写；数量必须一致；存储失败要体现在方案状态与日志中。
- 代码位置：`storage/result_store.py`、`storage/sqlite_store.py`。
- 追问：不一致怎么办？答：记录 storage_errors，不隐瞒。
- 范围：重复 run_id 不覆盖历史。

### Q41. 事务如何保证一致？
- 简洁回答：单条结果与检查项在同一事务写入，失败整体回滚。
- 深入：SQL 全部参数化；表结构含迁移逻辑（`ALTER TABLE ADD COLUMN`）。
- 代码位置：`storage/sqlite_store.py`。
- 追问：迁移会丢数据吗？答：只加列，不删历史。
- 范围：SQLite 单机。

### Q42. 历史记录会被覆盖吗？
- 简洁回答：不会。结果表冲突忽略，运行目录唯一，报告文件名带时间戳。
- 深入：`run_id` 由时间戳 + uuid 生成；报告以 `x` 模式写入，已存在即失败。
- 代码位置：`storage/`、`reports/generator.py::write_html_report`。
- 追问：同 run_id 重跑？答：不应发生；若发生不会静默覆盖结果。
- 范围：`finish_run` 是 UPDATE，需唯一 run_id 约束保证。

### Q43. 覆盖率 84% 怎么看待？
- 简洁回答：核心逻辑覆盖较高，未覆盖集中在交互与异常组合，已记录原因。
- 深入：557 项测试；核心引擎/仪器/存储多在 85%–100%；
  未覆盖项不是通过排除模块刷出来的。
- 代码位置：`docs/29_test_quality_report.md`、`pyproject.toml`。
- 追问：为什么不追求 100%？答：交互分支与极端 IO 异常成本高、收益低。
- 范围：无跳过测试。

### Q44. Streamlit 怎么测？
- 简洁回答：使用官方 AppTest，配合临时结果目录，验证六页与关键交互。
- 深入：覆盖空状态、真实执行、跨页状态、非法输入、超限扫描、
  报告生成与下载不重跑；不污染真实数据库。
- 代码位置：`tests/test_streamlit_app.py`、`tests/test_web_report_export.py`。
- 追问：视觉验收呢？答：只对实际打开过的页面声称完成，其余不宣称。
- 范围：无浏览器全量截图。

### Q45. 如何保证报告不触发重新测试？
- 简洁回答：报告生成器只读 SQLite 与运行目录，不 import 执行器。
- 深入：历史页的下载按钮只读取已生成文件；测试断言生成/下载前后结果数不变。
- 代码位置：`reports/generator.py`、`ui/views/history.py`。
- 追问：报告会重新计算指标吗？答：只展示已持久化指标与原始值，不重跑。
- 范围：不合并其他运行数据。

## 五、工程化、部署与反思（11 题）

### Q46. 统一路径解决了什么问题？
- 简洁回答：让本地、Docker、测试写入同一套可配置目录，避免写死。
- 深入：默认 `results/testlab.db` 不变；`TESTLAB_RESULTS_DIR` 优先，
  兼容旧变量；导入不创建目录。
- 代码位置：`core/paths.py`、`tests/test_project_paths.py`。
- 追问：Web 用户能改路径吗？答：不能，只由部署环境决定。
- 范围：不做多租户目录隔离。

### Q47. Docker 配置验证了吗？
- 简洁回答：写了 Dockerfile/compose，但本机没有 Docker，明确未验证。
- 深入：镜像基于 python:3.11-slim、非 root 用户、健康检查、结果卷；
  未执行 build/up，不宣称可用。
- 代码位置：`Dockerfile`、`compose.yaml`、`docs/30_release_validation.md`。
- 追问：怎么验证？答：在具备 Docker 的机器 build、up、health、备份恢复。
- 范围：NOT_VERIFIED。

### Q48. CI 怎么设计的？
- 简洁回答：Ubuntu + Windows 矩阵，安装依赖、pip check、ruff、pytest+coverage。
- 深入：未推送仓库，所以没有真实运行结果；README 不展示虚假徽章。
- 代码位置：`.github/workflows/ci.yml`。
- 追问：为什么两个系统？答：路径与文件锁差异大，需要跨平台验证。
- 范围：未执行。

### Q49. 备份脚本如何保证可靠？
- 简洁回答：SQLite 原生 backup、只读源、完整性检查、行数比对、不覆盖。
- 深入：文件名带 UTC 时间戳；恢复必须人工执行，脚本不自动覆盖数据库。
- 代码位置：`scripts/backup_database.py`、`docs/34_database_backup.md`。
- 追问：运行目录也备份吗？答：数据库与 JSONL 目录需分别备份，文档已说明。
- 范围：Docker 卷备份未验证。

### Q50. 开发中遇到的最大教训？
- 简洁回答：异常路径决定工程质量，而不是正常路径。
- 深入：清理失败、进度提前、历史覆盖、把当前配置当历史，都会让结果不可信；
  因此用确定性规则与显式状态解决。
- 代码位置：`engine/suite_runner.py`、`reports/generator.py`。
- 追问：怎么防止回归？答：针对性测试 + 验收脚本。
- 范围：仍有技术债。

### Q51. 如果重做，会改什么？
- 简洁回答：统一定义一次统计口径，并更早引入路径与报告抽象。
- 深入：先定义领域模型与状态机，再写 UI；复合故障测试提前设计；
  报告模板与测试同步开发。
- 代码位置：`reports/`、`engine/models.py`、`core/paths.py`。
- 追问：会换技术栈吗？答：当前栈足够；真实硬件阶段再评估。
- 范围：不做大重构。

### Q52. 项目有哪些明确局限？
- 简洁回答：仿真、无真实硬件、无纹波/瞬态、单进程、部署未实机验证。
- 深入：模型为稳态行为模型；Docker/Linux/CI 未验证；许可证未选定。
- 代码位置：`README.md`、`docs/28`–`docs/34`。
- 追问：这些局限影响求职展示吗？答：不影响，边界清楚反而是加分项。
- 范围：不夸大。

### Q53. 如何向非技术面试官介绍？
- 简洁回答：这是一个“虚拟实验室”，能自动跑测试、判断好坏、留下证据并
  生成可打印报告。
- 深入：强调解决了“测试可重复、结果可追溯、异常可处理”；
  用截图和报告展示，不用公式开场。
- 代码位置：`assets/screenshots/`、`results/reports/`。
- 追问：为什么不做真实硬件？答：成本与安全，模拟足以验证工程能力。
- 范围：不声称商业落地。

### Q54. 数据安全与隐私怎么考虑？
- 简洁回答：不提交数据库、日志、密钥；报告与路径限制在 results 下。
- 深入：`.gitignore` 排除 `.env`、数据库、日志；Web 导出只读；报告输出
  路径必须位于 results，拒绝路径穿越。
- 代码位置：`.gitignore`、`reports/generator.py`、`ui/service.py`。
- 追问：有敏感数据吗？答：没有真实客户或硬件数据。
- 范围：未实现登录鉴权。

### Q55. 后续 PowerLab / BatteryLab 如何接入？
- 简洁回答：按外部数据契约提供带来源与版本的数据，复用现有判定与报告。
- 深入：PowerLab 提供电路仿真指标，映射到现有字段；BatteryLab 需要新增
  容量/能量效率/温升等指标族，不能强套 DC-DC 效率。
- 代码位置：`docs/32_external_data_contract.md`、`engine/dut_bridge.py`。
- 追问：现在实现了吗？答：没有，只定义契约；本阶段不开发新项目。
- 范围：契约先行，实现待后续。

# 个人贡献说明（项目贡献拆分）

本文严格区分三类内容，避免把上游或依赖说成自主开发。

## 1. 自主设计与实现（本人完成）

### 1.1 测试架构与执行

- `engine/case_loader.py`：YAML 用例/方案加载、未知字段拒绝、限值校验；
- `engine/test_runner.py`：单用例执行、设置值回读校验、四态判定、
  清理验证、可靠性集成；
- `engine/suite_runner.py`：方案编排、强制停止、SKIP 生成、汇总与持久化；
- `engine/result_judge.py`：统一电压限值判定；
- `engine/models.py`：`TestCase/TestResult/TestSuite` 等数据结构。

### 1.2 仪器与数据

- `instruments/`：基于 PyVISA 的电源/DMM/负载封装、量程校验、
  统一 `InstrumentManager`；
- `configs/instruments.yaml`：三台虚拟仪器的 SCPI 定义；
- `models/virtual_dut.py`：12 V→5 V 行为模型与保护状态机；
- `bench/virtual_test_bench.py`、`engine/dut_bridge.py`：
  显式数据桥接与来源标签；
- `analysis/`：工程指标、数据质量、统计分析。

### 1.3 可靠性与存储

- `reliability/`：故障模型、注入器、异常分类、重试策略、事件日志、
  可靠性统计；
- `storage/result_store.py`：JSONL/CSV 运行目录与配置快照；
- `storage/sqlite_store.py`：SQLite 表结构、事务写入、迁移、查询。

### 1.4 Web 平台

- `ui/service.py`：唯一服务层、进程级任务锁、进度回调、历史与导出；
- `ui/views/`：六个页面；
- `ui/state.py`、`ui/theme.py`、`ui/formatters.py`、`ui/components.py`；
- `app.py`：入口与页面路由。

### 1.5 第十阶段工程化

- `core/paths.py`：统一路径与环境变量；
- `reports/generator.py`、`reports/templates/test_report.html`、
  `scripts/generate_report.py`：综合报告；
- `scripts/backup_database.py`：数据库备份与完整性校验；
- `scripts/verify_release.py`：发布验收；
- `scripts/start_windows.ps1`、`scripts/start_linux.sh`；
- `Dockerfile`、`.dockerignore`、`compose.yaml`；
- `.github/workflows/ci.yml`、`pyproject.toml`、`requirements-dev.txt`、
  `environment.yml`、`VERSION`、`CHANGELOG.md`、`LICENSE`（授权建议）、
  `THIRD_PARTY_NOTICES.md`；
- `tests/test_report_generator.py`、`test_database_backup.py`、
  `test_project_paths.py`、`test_release_validation.py`、
  `test_web_report_export.py`。

### 1.6 文档

`docs/01`–`docs/34`、`README.md`、`AGENTS.md`、`portfolio/` 均由本人编写。

## 2. 上游项目（未修改源码，不计自主开发）

| 项目 | 版本 | 许可证 | 使用方式 |
| --- | --- | --- | --- |
| PyVISA | 1.16.2 | MIT | 调用 VISA 资源管理与会话 API |
| PyVISA-sim | 0.7.1 | MIT | YAML 定义的虚拟仪器后端 |

本地 `pyvisa-sim-main/` 仅作阅读参考，运行时不加载，不修改。

## 3. 第三方依赖（库，不计自主开发）

PyYAML、numpy（间接）、pandas、plotly、streamlit、pytest、pytest-cov、ruff。
许可证见 `THIRD_PARTY_NOTICES.md`。

## 4. 明确未完成 / 未验证

- 未接入真实硬件；
- 未实现纹波、瞬态响应；
- Docker 未构建（本机无 Docker）；
- Linux 未实机部署；
- GitHub Actions 未推送运行；
- 未实现 PowerLab / BatteryLab；
- 许可证未选定。

## 5. 可量化的验证证据

| 项目 | 证据 |
| --- | --- |
| 测试 | 557 passed（`pytest tests -q`） |
| 覆盖率 | 84%（`docs/29_test_quality_report.md`） |
| 静态检查 | `ruff check .` 0 错误 |
| 发布验收 | `scripts.verify_release` 核心 7/7 PASS |
| 真实历史 | `results/testlab.db` 与 `results/automation/run_<id>/` |
| 报告 | `results/reports/test_report_<run_id>_*.html` |
| 可靠性 | F001–F009 场景与 `docs/23_phase8_acceptance.md` |
| Web | AppTest 六页渲染与交互测试 |

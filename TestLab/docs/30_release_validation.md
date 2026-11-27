# 30 发布验收记录（scripts/verify_release.py）

## 1. 验收方式

```powershell
conda run -n kaifa python -m scripts.verify_release
```

- 使用 `tempfile.TemporaryDirectory()` 作为结果目录与数据库位置；
- 不写入 `results/testlab.db`，不生成虚假结果；
- 核心检查失败返回退出码 1；未执行项输出 `NOT_VERIFIED`。

## 2. 实际输出（2026-11-24）

```text
TestLab 发布验收（临时结果目录，不污染真实历史）
====================================================================
[PASS] Python 版本: 3.11.18
[PASS] 核心依赖导入: 12 个核心模块导入成功
[PASS] 配置文件: 9 个 YAML 配置存在且可解析
[PASS] 虚拟仪器资源发现: 发现 3 个资源；psu/dmm/load 可解析
[PASS] VirtualDUT 模型计算: NORMAL, vout=4.9800 V, efficiency=0.9000
[PASS] 项目版本文件: 1.0.0
[PASS] 自动化执行 + 故障注入 + 数据库 + 综合报告:
       SUITE-SMOKE PASS=2 FAIL=0 ERROR=0；
       F001 注入事件 1 次，业务状态 PASS；
       报告 test_report_<run_id>_<timestamp>_<uuid>.html
[NOT_VERIFIED] Docker：当前环境未安装或不可用，仅保留配置。
[NOT_VERIFIED] Linux 服务器部署：本机为 Windows，需在目标机验证。
[NOT_VERIFIED] GitHub Actions：尚未推送仓库，需推送后查看真实运行结果。
====================================================================
发布验收核心检查全部通过；未执行项已标记 NOT_VERIFIED。
```

说明：SUITE-SMOKE 只有 2 条用例；F001 注入 1 次超时，按重试策略恢复后
业务状态为 PASS，这属于可靠性实验的预期现象，不是伪造。

## 3. 检查项说明

| 检查项 | 实际内容 |
| --- | --- |
| Python 版本 | 要求 >= 3.11 |
| 核心依赖导入 | core/instruments/models/bench/analysis/engine/storage/reliability/ui/reports |
| 配置文件 | 9 个 YAML 存在且为映射 |
| 虚拟仪器资源 | PyVISA-sim 发现 3 个资源，psu/dmm/load 可解析 |
| VirtualDUT | 12 V / 1 A 计算为 NORMAL，vout 4.98 V |
| 项目版本 | 读取 `VERSION` |
| 自动化执行 | 临时目录执行 SUITE-SMOKE，无 ERROR |
| 故障注入 | F001 产生真实注入事件 |
| 数据库结构 | 临时数据库包含 runs/test_results/check_results/fault_events |
| 综合报告 | 生成非空 HTML，包含 run_id |
| Docker | 本机未安装 docker，配置保留，NOT_VERIFIED |
| Linux | 未在 Linux 实机执行，NOT_VERIFIED |
| GitHub Actions | 未推送，NOT_VERIFIED |

## 4. 未验证事项（不得视为成功）

1. **Docker 镜像构建与运行**：`docker --version` 不可用；`Dockerfile`、
   `.dockerignore`、`compose.yaml` 按规格编写，未经构建验证。
2. **Linux 部署**：本机为 Windows，`scripts/start_linux.sh` 未在 Linux 执行。
3. **GitHub Actions**：仓库无 remote、未推送，`ci.yml` 未产生真实运行记录。
4. **浏览器视觉验收**：仅覆盖本阶段实际打开过的页面，其余页面以 AppTest
   渲染结果为准，不宣称已完成全部视觉验收。

## 5. 验收结论

- 核心本地发布验收通过（7/7 PASS）；
- 外部环境相关项目 3 项 NOT_VERIFIED，需在具备 Docker/Linux/远程仓库权限后
  单独验证；
- 该结果与 `docs/33_final_delivery_report.md` 保持一致。

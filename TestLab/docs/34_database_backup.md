# 34 数据库备份与恢复操作说明

## 1. 备份范围

`scripts/backup_database.py` 只使用 SQLite 原生 `backup` 接口复制**数据库**
（`results/testlab.db`）。以下内容**不在**数据库备份内，需要单独管理：

- `results/automation/run_<run_id>/`：JSONL/CSV、配置快照、执行日志；
- `results/reliability/run_<run_id>/`：可靠性事件与图表；
- `results/reports/`：综合 HTML 报告；
- `results/**` 下的扫描 CSV/HTML。

建议把 `results/` 整体纳入独立备份策略，并为其保留与数据库一致的保留周期。

## 2. 创建备份

```powershell
# 默认备份到 results/backups/
& "C:\\Users\\<user>\.conda\envs\kaifa\python.exe" -m scripts.backup_database

# 指定目录
& "C:\\Users\\<user>\.conda\envs\kaifa\python.exe" -m scripts.backup_database --backup-dir D:\testlab-backups

# 查看已有备份
& "C:\\Users\\<user>\.conda\envs\kaifa\python.exe" -m scripts.backup_database --list
```

Linux：

```bash
python -m scripts.backup_database --backup-dir "$HOME/testlab-backups"
```

特性：

- 以只读 URI 打开源库，不修改原始数据；
- 文件名 `testlab_<UTC时间戳>_<微秒>Z.db`，**已存在则报错，不覆盖**；
- 备份后执行 `PRAGMA integrity_check`，并比对
  `runs/test_results/check_results/fault_events` 行数；
- 不删除原始数据库；不自动执行恢复。

## 3. 恢复步骤（手动，必须确认）

> 恢复会覆盖当前数据库，必须由人工执行；脚本不会自动恢复。

1. **停止所有写入任务**：
   - 停止 Streamlit（`Ctrl+C` 或 `docker compose down`）；
   - 确认没有 `pytest`、`scripts.run_test_suite`、`scripts.reliability_demo`
     等进程在写数据库。
2. **先备份当前数据库**：
   ```powershell
   python -m scripts.backup_database --backup-dir D:\testlab-backups-before-restore
   ```
3. **保留现场再替换**（不要直接删除原文件）：
   ```powershell
   Move-Item results\testlab.db results\testlab.db.before-restore
   Copy-Item D:\testlab-backups\testlab_20261124T093554_827041Z.db results\testlab.db
   ```
   Linux：
   ```bash
   mv results/testlab.db results/testlab.db.before-restore
   cp ~/testlab-backups/testlab_<timestamp>.db results/testlab.db
   ```
4. **验证**：
   ```powershell
   python -m scripts.backup_database --list
   python -m scripts.query_test_history --list
   ```
   并确认：
   - `PRAGMA integrity_check` 为 `ok`；
   - 运行数量、用例数量符合预期；
   - `results/automation/` 中对应运行目录仍存在（数据库恢复不会恢复目录，
     历史目录需另行从备份恢复）。
5. **重新启动应用**并检查历史页与报告生成。

## 4. 恢复后的注意事项

- 数据库与 JSONL/运行目录必须来自同一时间点，否则报告会提示快照缺失；
- 如果只恢复数据库而缺少运行目录，报告仍可生成，但 DUT 参数与限值会显示
  “无法追溯（缺少配置快照）”；
- 不要用旧数据库覆盖新数据库后继续写入同一 `run_id`；
- 不要在应用运行中直接复制 `.db` 文件（可能得到不一致副本），应使用本脚本。

## 5. 备份策略建议

| 场景 | 建议 |
| --- | --- |
| 本机开发 | 每次重要验收前备份一次 |
| 长期演示 | 每日备份数据库，并保留最近 7 份 |
| Docker 部署 | 备份命名卷 `testlab_results`（未在本机验证） |
| 交付前 | 数据库 + `results/` 全目录 + `VERSION`/`CHANGELOG.md` 一并归档 |

## 6. 状态

- 本机已完成数据库备份与完整性校验（见 `docs/33_final_delivery_report.md`）；
- Docker 卷备份与 Linux 定时备份未在本机执行（NOT_VERIFIED）。

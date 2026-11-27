# BatteryLab 交付与复现说明（v2）

## 1. 环境

```powershell
conda run --no-capture-output -n kaifa_battery python -B -m <module>
```

## 2. 复现命令（按顺序）

```powershell
python -B -m scripts.hardening_baseline
python -B -m scripts.hardening_afe
python -B -m scripts.hardening_protection
python -B -m scripts.hardening_charging
python -B -m scripts.hardening_ecm
python -B -m scripts.hardening_system
python -B -m scripts.hardening_domain
python -B -m scripts.hardening_eda
python -B -m scripts.audit_resume_metrics
python -B -m scripts.hardening_portfolio_v2
python -B -m pytest tests -q
```

## 3. 产物位置

- 新增分析结果：`results/hardening/<area>/run_<id>/`
- v2 六件套：`portfolio/BatteryLab_*_v2.md`、`portfolio/BatteryLab_resume_metrics_v2.csv`
- Task 22 专题报告：`portfolio/BatteryLab_研发能力补强报告.md` 等 7 份
- 历史运行：未覆盖，仍保留在原目录

## 4. 约束

- TestLab / PowerLab 未修改；未提交 Git；未安装 KiCad；未采购、未制板、未做真实锂电池上电。

# GitHub 发布前清单（更新版）

生成日期：2026-11-27　目标账号：`gazh666`（待 `gh api user` 实测确认）　目标仓库：`Electronics-Engineering-Portfolio`

> 状态：文件清单、许可证、敏感信息扫描已完成；仓库按 **Private 优先** 创建，远程验证后再由所有者确认是否转为 Public。

## 1. 仓库内容

| 项目 | 结果 |
|---|---|
| 目录 | `Electronics-Engineering-Portfolio`（独立，不在三个原始项目内） |
| 文件数 | 1328（含本清单、清单 CSV 与安全扫描 JSON） |
| 总体积 | ≈ 15.4 MB（远低于 100 MB 限制） |
| 最大单文件 | `board.step`（< 5 MB） |
| 是否包含 `.env` / 密钥文件 | 否 |
| 是否包含 `results/` `storage/` `deliverables/` | 否（已在 `.gitignore`） |
| 是否包含嵌套 `.git` | 否 |
| 是否包含第三方二进制（FreeRouting / KiCad 安装包） | 否 |

## 2. 敏感信息扫描结果

详细结果见 `docs/security_scan_summary.json`，逐文件清单见 `docs/publication_manifest.csv`。

| 检查 | 结果 |
|---|---|
| GitHub Token / AWS Key / 私钥 / Slack Token 模式 | **0** |
| 邮箱地址 | **0** |
| 本机绝对路径（工作区盘符路径、用户目录路径） | **0**（已批量清洗为相对路径与 `C:\Users\<user>`） |
| `.env*` / 私钥 / 证书文件 | **0** |
| 本地数据库（`.db/.sqlite/...`） | **0** |
| 大文件（>5 MB） | **0** |
| FreeRouting ASCII 工作目录 | 位于仓库外，**未随仓库分发**；仓库内无其日志或路径 |

## 3. 许可证状态

- 原创及 AI 辅助代码、文档、原创符号：**MIT**（`LICENSE`）。
- 第三方组件、数据、模型、封装、工具：保留各自许可证（`THIRD_PARTY_NOTICES.md`）。
- FreeRouting（AGPL-3.0）程序本体与工作目录**未上传**。

## 4. 上传前置条件

| 条件 | 状态 |
|---|---|
| Git 已安装 | 是（2.55.0） |
| Git 身份 | 仓库级配置（优先 GitHub noreply 邮箱） |
| GitHub CLI (`gh`) | 待安装（`winget install --id GitHub.cli --exact`） |
| 推送凭据 | 待 `gh auth login --web`（浏览器授权，不使用粘贴 PAT） |
| 用户授权上传 | **已获得**（同意上传、MIT、Private 优先） |

## 5. 执行步骤

```powershell
git init -b main
git status --short
git add -- .
git diff --cached --stat
git diff --cached --name-only     # 再次核查暂存内容
git commit -m "Publish electronics engineering research portfolio"
gh repo create Electronics-Engineering-Portfolio --private --source . --remote origin --push
gh repo view --json nameWithOwner,url,visibility,defaultBranchRef
```

> 禁止强制推送；禁止修改其他远程仓库；转为 Public 必须等待所有者明确确认。

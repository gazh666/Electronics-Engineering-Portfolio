# 31 Linux 服务器部署指南

本指南提供两种部署方式。当前环境为 Windows，**本文未在 Linux 实机执行验证**，
相关步骤标记为待验证；不得据此宣称已在服务器部署成功。

## 0. 前置检查

```bash
python3 --version        # 需要 3.11（或确认可用的 conda 环境）
ss -ltnp | grep 8501     # 检查端口占用
```

- 不修改服务器现有 base、CUDA、PyTorch 等科研环境；
- 不需要 `sudo` 安装 Python 依赖；
- 默认只监听 `127.0.0.1`，不开放公网端口；
- 数据库与报告写入 `results/`，可通过 `TESTLAB_RESULTS_DIR` 指向独立目录。

## 方案 A：独立 Python 虚拟环境

```bash
git clone <你的仓库地址> TestLab     # 或手动上传项目目录
cd TestLab

python3.11 -m venv ~/.venvs/testlab
source ~/.venvs/testlab/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check

bash scripts/start_linux.sh
```

等价的手动启动：

```bash
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

自定义结果目录：

```bash
export TESTLAB_RESULTS_DIR="$HOME/testlab-results"
mkdir -p "$TESTLAB_RESULTS_DIR"
bash scripts/start_linux.sh
```

停止：在运行终端按 `Ctrl+C`。

若服务器没有 Python 3.11：

1. 优先确认是否已安装 conda，可创建独立环境：
   ```bash
   conda create -n testlab python=3.11 -y
   conda activate testlab
   python -m pip install -r requirements.txt
   ```
2. 不要覆盖或删除现有科研环境；不要用系统 Python 强行安装。

## 方案 B：Docker Compose

仅在服务器已具备 Docker 权限时执行。

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100
curl -s http://127.0.0.1:8501/_stcore/health
docker compose exec testlab python -m pip check
```

- `compose.yaml` 默认把端口发布到 `127.0.0.1:8501`；
- 使用命名卷 `testlab_results` 持久化 SQLite 与报告；
- 容器重建后历史数据不消失；
- 不要执行 `docker compose down -v`（会删除历史数据卷）；
- 停止：`docker compose down`。

访问方式（SSH 端口转发，推荐）：

```bash
ssh -N -L 18501:127.0.0.1:8501 用户名@服务器地址
```

然后在本机浏览器打开 <http://localhost:18501>。

## 3. 数据与备份

- 结果目录结构：`results/automation/`、`results/reliability/`、
  `results/reports/`、`results/testlab.db`；
- 备份命令（在项目根目录）：
  ```bash
  python -m scripts.backup_database --backup-dir "$HOME/testlab-backups"
  ```
- 恢复步骤见 `docs/34_database_backup.md`；
- Docker 卷备份需在宿主机执行（本阶段未验证）。

## 4. 安全边界

- 本阶段不配置公网访问、HTTPS、身份认证或反向代理；
- 如未来需要公网演示，必须单独完成：身份认证、TLS、访问控制、日志审计；
- 不在仓库保存 `.env`、数据库、日志或密钥；
- 不在生产服务器挂载整个用户主目录或 Docker Socket。

## 5. 验证状态

| 项目 | 状态 |
| --- | --- |
| `scripts/start_linux.sh` 语法与路径 | 已编写，未在 Linux 执行（NOT_VERIFIED） |
| 方案 A venv 安装 | 未在 Linux 执行（NOT_VERIFIED） |
| 方案 B Docker Compose | 本机无 Docker，未执行（NOT_VERIFIED） |
| SSH 端口转发 | 未连接服务器，未执行（NOT_VERIFIED） |

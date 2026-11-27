"""统一项目路径与运行目录。

优先级
------
1. ``TESTLAB_RESULTS_DIR``：容器/部署环境使用（Dockerfile、compose.yaml）；
2. ``TESTLAB_RESULTS_ROOT``：阶段九 AppTest 使用的历史变量名，保持兼容；
3. 项目内 ``results/``：本地默认位置，不改变既有数据库路径。

数据库路径默认是 ``<结果目录>/testlab.db``，可用 ``TESTLAB_DB_PATH`` 单独覆盖。

约束
----
- 环境变量只用于配置运行环境，Web 页面不允许用户指定任意本地路径；
- 导入本模块不会创建任何目录，``ensure_runtime_directories()`` 需显式调用；
- 所有路径均使用 ``pathlib``，不依赖 Windows 分隔符。
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"


def _resolve_env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def results_dir() -> Path:
    """返回当前配置的结果目录（在调用时读取环境变量）。"""
    override = _resolve_env_path("TESTLAB_RESULTS_DIR") or _resolve_env_path(
        "TESTLAB_RESULTS_ROOT"
    )
    return override or DEFAULT_RESULTS_DIR


def database_path() -> Path:
    """返回 SQLite 数据库路径（在调用时读取环境变量）。"""
    override = _resolve_env_path("TESTLAB_DB_PATH")
    if override is not None:
        return override
    return results_dir() / "testlab.db"


#: 导入时快照，供模块级默认值使用；需要感知运行时环境变量时请调用函数。
RESULTS_DIR = results_dir()
DATABASE_PATH = database_path()


def ensure_runtime_directories() -> Path:
    """创建结果目录并返回路径；仅在真正需要写入时调用。"""
    target = results_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target

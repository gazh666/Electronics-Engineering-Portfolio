"""TestLab 基础设施包：统一项目路径与运行目录配置。"""

from .paths import (
    CONFIG_DIR,
    DATABASE_PATH,
    DEFAULT_RESULTS_DIR,
    PROJECT_ROOT,
    RESULTS_DIR,
    database_path,
    ensure_runtime_directories,
    results_dir,
)

__all__ = [
    "PROJECT_ROOT",
    "CONFIG_DIR",
    "DEFAULT_RESULTS_DIR",
    "RESULTS_DIR",
    "DATABASE_PATH",
    "results_dir",
    "database_path",
    "ensure_runtime_directories",
]

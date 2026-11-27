"""SQLite 数据库备份（使用 sqlite3 原生 backup 接口）。

示例::

    conda run -n kaifa python -m scripts.backup_database
    conda run -n kaifa python -m scripts.backup_database --list
    conda run -n kaifa python -m scripts.backup_database --backup-dir D:\\backups

约束
----
- 以只读 URI 打开源数据库，不修改、不删除原始数据；
- 备份文件名带 UTC 时间戳，已存在则报错，绝不覆盖；
- 备份完成后执行 ``PRAGMA integrity_check`` 并比对主要表行数；
- 本脚本不自动执行恢复；恢复步骤见 ``docs/34_database_backup.md``。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import DATABASE_PATH, RESULTS_DIR  # noqa: E402

DEFAULT_BACKUP_DIR = RESULTS_DIR / "backups"
TABLES = ("runs", "test_results", "check_results", "fault_events")


class BackupError(RuntimeError):
    """备份失败（源缺失、目标已存在、完整性校验失败等）。"""


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TABLES:
        row = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if row and int(row[0]):
            counts[table] = int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
    return counts


def backup_database(
    source_path: str | Path | None = None,
    backup_dir: str | Path | None = None,
) -> Path:
    """创建一致性快照并验证完整性，返回备份路径。"""
    source = Path(source_path) if source_path is not None else DATABASE_PATH
    source = source.expanduser().resolve()
    if not source.is_file():
        raise BackupError(f"源数据库不存在: {source}")

    target_dir = Path(backup_dir) if backup_dir is not None else DEFAULT_BACKUP_DIR
    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    destination = target_dir / f"testlab_{stamp}.db"
    if destination.exists():
        raise BackupError(f"备份文件已存在，拒绝覆盖: {destination}")

    source_uri = source.as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_conn:
        source_counts = _table_counts(source_conn)
        with closing(sqlite3.connect(destination)) as target_conn:
            source_conn.backup(target_conn)
            integrity = target_conn.execute("PRAGMA integrity_check").fetchall()
            if integrity != [("ok",)]:
                raise BackupError(f"备份完整性校验失败: {integrity}")
            target_counts = _table_counts(target_conn)

    if source_counts != target_counts:
        raise BackupError(
            f"备份记录数不一致: 源={source_counts} 备份={target_counts}"
        )
    return destination


def _list_backups(backup_dir: Path) -> int:
    if not backup_dir.is_dir():
        print(f"备份目录不存在: {backup_dir}")
        return 0
    files = sorted(backup_dir.glob("testlab_*.db"))
    if not files:
        print("暂无备份文件。")
        return 0
    for path in files:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        print(f"{path.name}  {path.stat().st_size} B  {mtime}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="备份 TestLab SQLite 数据库")
    parser.add_argument("--source", default=str(DATABASE_PATH))
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--list", action="store_true", help="列出已有备份")
    args = parser.parse_args(argv)

    backup_dir = Path(args.backup_dir)
    if args.list:
        return _list_backups(backup_dir)

    try:
        destination = backup_database(args.source, backup_dir)
    except (BackupError, sqlite3.Error, OSError) as exc:
        print(f"备份失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print("数据库备份完成：")
    print(f"  源: {Path(args.source).resolve()}")
    print(f"  备份: {destination}")
    print(f"  大小: {destination.stat().st_size} 字节")
    print("  完整性: PRAGMA integrity_check = ok，主要表行数一致")
    print("  恢复前请先停止写入任务，并先备份现有数据库（详见 docs/34_database_backup.md）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

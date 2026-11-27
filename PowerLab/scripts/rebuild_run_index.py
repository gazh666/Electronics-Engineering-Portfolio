"""重建运行索引脚本（第九阶段 Task 6）。

用法：
    conda run -n kaifa_power python -m scripts.rebuild_run_index
"""

from __future__ import annotations

import argparse

from storage.run_index import build_index, index_path, save_index


def main() -> int:
    parser = argparse.ArgumentParser(description="rebuild PowerLab run index")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    index = build_index()
    path = save_index(index)
    stats = index.stats()
    if not args.quiet:
        print(f"index written: {path}")
        print(f"runs: {stats['total']}")
        print(f"by kind: {stats['by_kind']}")
        print(f"by data source: {stats['by_data_source']}")
        print(f"by status: {stats['by_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

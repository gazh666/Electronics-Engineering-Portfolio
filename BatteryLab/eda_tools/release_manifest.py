"""工程交付文件哈希清单。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def create_release_manifest(
    artifact_directory: str | Path,
    output_path: str | Path,
    extra_metadata: dict | None = None,
) -> dict:
    root = Path(artifact_directory).resolve()
    output = Path(output_path).resolve()

    if not root.is_dir():
        raise FileNotFoundError(root)

    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve() == output:
            continue
        records.append(
            {
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )

    if not records:
        raise ValueError("No release artifacts")

    manifest = {
        "release_type": "ENGINEERING_DESIGN_ONLY",
        "hardware_validated": False,
        "production_released": False,
        "artifact_root": str(root),
        "file_count": len(records),
        "files": records,
    }
    if extra_metadata:
        manifest.update(extra_metadata)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest

"""Package a reviewed allowlist; exclude secrets, original data and local environments."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "README.md",
    "RUN.md",
    "DEMO.md",
    "DATA_SOURCES.md",
    "ARCHITECTURE.md",
    "pyproject.toml",
    "uv.lock",
    "Dockerfile",
    "compose.yaml",
    "compose.offline.yaml",
    "start-offline.cmd",
    "mcp-config.json",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    ".gitattributes",
    "data/manifest.json",
    "data/replay.json",
    ".github/workflows/ci.yml",
    ".cursor/mcp.json",
]
DIRECTORIES = ["src", "tests", "docs", "examples", "scripts"]


def main() -> None:
    files = [ROOT / name for name in FILES]
    for directory in DIRECTORIES:
        files.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}
        )
    paths = sorted(set(files))
    if any(not p.is_file() for p in paths):
        raise RuntimeError("required delivery file missing")
    target = ROOT / "dist" / "mining-brief-demo.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, "mining-brief-demo/" + path.relative_to(ROOT).as_posix())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".sha256").write_text(digest + "  " + target.name + "\n", encoding="ascii")
    print(
        json.dumps(
            {
                "archive": str(target),
                "files": len(paths),
                "bytes": target.stat().st_size,
                "sha256": digest,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

"""校验：Docker 镜像里实际安装的项目版本是否与当前源码一致。

build 完成后运行本脚本（Windows: `.venv\\Scripts\\python.exe scripts\\verify_image_revision.py`），
或由 package_offline.py 在导出前自动调用。任何一项不一致就以非零码退出，
避免把旧代码镜像当成当前版本交付。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "mining-brief:demo"
CHECKED_FILES = sorted(path.relative_to(ROOT).as_posix() for path in ROOT.glob("src/**/*.py")) + [
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "data/manifest.json",
    "data/replay.json",
]


def image_digests(image: str) -> dict[str, str]:
    """在交付镜像的容器内计算同名单文件哈希。"""
    script = (
        "import hashlib, json, pathlib;"
        "print(json.dumps({p: hashlib.sha256(pathlib.Path('/app', p).read_bytes()).hexdigest()"
        " for p in json.loads(r'" + json.dumps(CHECKED_FILES) + "')}))"
    )
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            image,
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]


def main() -> None:
    local = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CHECKED_FILES}
    inside = image_digests(IMAGE)
    differences = {name: {"repo": local[name], "image": inside.get(name)} for name in CHECKED_FILES}
    mismatched = {k: v for k, v in differences.items() if v["repo"] != v["image"]}
    report = {
        "image": IMAGE,
        "checked_files": len(CHECKED_FILES),
        "consistent": not mismatched,
        "mismatched": mismatched,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if mismatched:
        print(
            "镜像内的代码与当前源码不一致；请先 docker compose build agent 后重新验证。",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

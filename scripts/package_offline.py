"""Create a local offline handoff including the already-built project image."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from package_delivery import DIRECTORIES, FILES, ROOT


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_image_revision() -> dict[str, object]:
    """导出前确认镜像里的代码就是当前源码，避免交付旧版本镜像。"""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_image_revision.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "镜像内的代码与当前源码不一致，拒绝导出；先运行 docker compose build agent。"
        )
    return json.loads(completed.stdout.strip())  # type: ignore[no-any-return]


def main() -> None:
    revision = verify_image_revision()
    print(json.dumps({"image_revision": revision}, ensure_ascii=False), flush=True)
    image_ref = "mining-brief:demo"
    inspection = subprocess.run(
        ["docker", "image", "inspect", image_ref],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    inspected = json.loads(inspection.stdout)[0]
    destination = ROOT / "dist" / "mining-brief-offline"
    destination.mkdir(parents=True, exist_ok=True)
    image_archive = destination / "mining-brief-image.tar.gz"
    export_record = destination / "offline-manifest.json"
    existing = (
        json.loads(export_record.read_text(encoding="utf-8")) if export_record.exists() else {}
    )
    if not (
        image_archive.exists()
        and existing.get("image_id") == inspected["Id"]
        and existing.get("image_sha256") == checksum(image_archive)
    ):
        print("Exporting only the mining-brief project image...", flush=True)
        temporary = image_archive.with_suffix(".partial")
        with (destination / "export.stderr.log").open("wb") as errors:
            process = subprocess.Popen(
                ["docker", "image", "save", image_ref],
                stdout=subprocess.PIPE,
                stderr=errors,
            )
            try:
                assert process.stdout is not None
                with (
                    temporary.open("wb") as raw,
                    gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as archive,
                ):
                    shutil.copyfileobj(process.stdout, archive, length=1024 * 1024)
                if process.wait() != 0:
                    raise RuntimeError("Docker image export failed; see export.stderr.log")
                temporary.replace(image_archive)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if process.stdout is not None:
                    process.stdout.close()
                if temporary.exists():
                    temporary.unlink()
    with tarfile.open(image_archive, "r:gz") as exported:
        metadata = exported.extractfile("manifest.json")
        if metadata is None:
            raise RuntimeError("The Docker archive has no manifest")
        platforms = json.load(metadata)
        selected = next(item for item in platforms if image_ref in item.get("RepoTags", []))
        config_digest = "sha256:" + Path(selected["Config"]).name.removesuffix(".json")
    manifest = {
        "schema_version": "1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "image_ref": image_ref,
        "image_id": inspected["Id"],
        "image_config_id": config_digest,
        "image_archive": image_archive.name,
        "image_sha256": checksum(image_archive),
        "image_bytes": image_archive.stat().st_size,
        "platform": inspected["Os"] + "/" + inspected["Architecture"],
        "data_mode": "historical replay: 2021-09-08",
        "requires": "Docker Desktop installed and running with Linux containers",
    }
    export_record.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    sources = {ROOT / name for name in [*FILES, "compose.offline.yaml", "start-offline.cmd"]}
    for directory in DIRECTORIES:
        sources.update(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}
        )
    for source in sources:
        target = destination / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    archive_path = ROOT / "dist" / "mining-brief-offline.zip"
    with ZipFile(archive_path, "w") as archive:
        for source in sorted(sources):
            relative = source.relative_to(ROOT).as_posix()
            archive.write(
                destination / relative,
                "mining-brief-offline/" + relative,
                compress_type=ZIP_DEFLATED,
            )
        for source in (image_archive, export_record):
            archive.write(source, "mining-brief-offline/" + source.name, compress_type=ZIP_STORED)
    digest = checksum(archive_path)
    archive_path.with_suffix(".sha256").write_text(
        digest + "  " + archive_path.name + "\n", encoding="ascii"
    )
    print(
        json.dumps(
            {
                "archive": str(archive_path),
                "bytes": archive_path.stat().st_size,
                "sha256": digest,
                "image_id": inspected["Id"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

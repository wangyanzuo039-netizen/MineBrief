from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from typing import Any

from mining_brief.config import Settings
from mining_brief.network import SourceError, download, original_path


def verify(content: bytes, entry: dict[str, Any]) -> None:
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise SourceError("source_hash_mismatch", "来源文件校验值与已核验版本不一致")
    if entry["kind"] == "pdf" and not content.startswith(b"%PDF-"):
        raise SourceError("invalid_pdf", "来源不是有效 PDF")


async def load_original(settings: Settings, entry: dict[str, Any]) -> bytes:
    local = original_path(settings, entry)
    if settings.mode == "demo":
        if not local.exists():
            raise SourceError("missing_data", "原文缓存缺失，请运行 mining-brief prepare")
        content = local.read_bytes()
        verify(content, entry)
        return content
    content = await download(entry["url"], settings)
    # Registered report metadata belongs to one reviewed version, in both modes.
    try:
        verify(content, entry)
    except SourceError as exc:
        # 在线来源更新为新版本时，必须报出版本变化，而不是套用旧元数据。
        if exc.code == "source_hash_mismatch":
            raise SourceError(
                "source_version_changed",
                "在线来源内容与已核验版本不一致；需人工核验后再更新 manifest，不套用旧元数据",
            ) from exc
        raise
    return content


async def prepare(settings: Settings, *, include_live: bool = False) -> list[dict[str, str]]:
    manifest = settings.manifest()
    ids = set(
        manifest["demo_news_ids"] + [manifest["demo_report_id"], manifest["ni_report_id"], "lme-lh"]
    )
    if include_live:
        ids.add(manifest["live_report_id"])

    async def one(entry: dict[str, Any]) -> dict[str, str]:
        target = original_path(settings, entry)
        if target.exists():
            verify(target.read_bytes(), entry)
            return {"source_id": entry["id"], "status": "verified_cache"}
        target.parent.mkdir(parents=True, exist_ok=True)
        content = await download(entry["url"], settings)
        verify(content, entry)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix="download-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return {"source_id": entry["id"], "status": "downloaded_verified"}

    return list(
        await asyncio.gather(*(one(entry) for entry in manifest["sources"] if entry["id"] in ids))
    )

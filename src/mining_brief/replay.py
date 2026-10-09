"""Validated extraction cache for repeatable demos without redistributing originals."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from mining_brief.config import Settings
from mining_brief.network import SourceError, original_path
from mining_brief.schemas import ToolResult


def load_replay(settings: Settings) -> dict[str, Any]:
    manifest = settings.manifest()
    entry = manifest.get("replay")
    if not entry:
        raise SourceError("missing_replay", "演示提取缓存缺失，请取得完整源码版本")
    content = original_path(settings, entry).read_bytes()
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise SourceError("replay_hash_mismatch", "演示提取缓存校验失败")
    data: dict[str, Any] = json.loads(content)
    if data.get("schema_version") != "1.0" or data.get("as_of") != manifest["demo_as_of"]:
        raise SourceError("replay_version_mismatch", "提取缓存版本或分析日期不符")
    return data


def extracted(settings: Settings, kind: str, entry: dict[str, Any]) -> dict[str, Any]:
    replay = load_replay(settings)
    cached = replay[kind].get(entry["id"])
    if cached is None or cached["original_sha256"] != entry["sha256"]:
        raise SourceError("replay_source_mismatch", "提取缓存与登记原文版本不符")
    checked = ToolResult.model_validate(copy.deepcopy(cached["result"]))
    payload = checked.model_dump(mode="json")
    payload["meta"]["evidence_origin"] = "verified_extraction_cache"
    payload["meta"]["original_sha256"] = cached["original_sha256"]
    return payload

import hashlib
from unittest.mock import AsyncMock

import pytest

from mining_brief.config import Settings
from mining_brief.data import load_original
from mining_brief.network import SourceError
from mining_brief.providers.pdf import PDFProvider


@pytest.mark.parametrize("changed", [False, True])
async def test_live_registered_report_cannot_silently_change_version(
    monkeypatch, tmp_path, changed
):
    reviewed = b"%PDF-1.4 reviewed report, effective 2024-05-15"
    downloaded = reviewed.replace(b"2024", b"2030") if changed else reviewed
    entry = {
        "kind": "pdf",
        "path": "report.pdf",
        "url": "https://www.asx.com.au/report.pdf",
        "sha256": hashlib.sha256(reviewed).hexdigest(),
    }
    monkeypatch.setattr("mining_brief.data.download", AsyncMock(return_value=downloaded))
    settings = Settings(mode="live", data_dir=tmp_path)
    if changed:
        with pytest.raises(SourceError) as caught:
            await load_original(settings, entry)
        # 在线来源换版本时必须报出版本变化，而不是套用已登记的旧元数据。
        assert caught.value.code == "source_version_changed"
    else:
        assert await load_original(settings, entry) == reviewed


def test_demo_missing_or_mismatched_cache_keeps_original_error_codes(tmp_path):
    import asyncio

    entry = {
        "kind": "pdf",
        "path": "report.pdf",
        "url": "https://www.asx.com.au/report.pdf",
        "sha256": hashlib.sha256(b"reviewed").hexdigest(),
    }
    settings = Settings(mode="demo", data_dir=tmp_path)
    with pytest.raises(SourceError) as missing:
        asyncio.run(load_original(settings, entry))
    assert missing.value.code == "missing_data"
    (tmp_path / "report.pdf").write_bytes(b"changed")
    with pytest.raises(SourceError) as mismatched:
        asyncio.run(load_original(settings, entry))
    assert mismatched.value.code == "source_hash_mismatch"


async def test_unregistered_pdf_version_is_rejected_before_assuming_metadata(monkeypatch):
    monkeypatch.setattr(
        "mining_brief.providers.pdf.download", AsyncMock(return_value=b"%PDF-1.4 unseen report")
    )
    with pytest.raises(SourceError) as caught:
        await PDFProvider(Settings(mode="live")).extract_resources("https://www.asx.com.au/new.pdf")
    assert caught.value.code == "unverified_pdf_version"

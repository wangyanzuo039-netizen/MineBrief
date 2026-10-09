import hashlib
import shutil
from unittest.mock import AsyncMock

import pytest

from mining_brief.config import ROOT, Settings
from mining_brief.network import SourceError
from mining_brief.providers.news import NewsProvider
from mining_brief.providers.pdf import PDFProvider
from mining_brief.providers.price import PriceProvider
from mining_brief.replay import extracted, load_replay


def copied(tmp_path):
    for name in ("manifest.json", "replay.json"):
        shutil.copyfile(ROOT / "data" / name, tmp_path / name)
    return Settings(data_dir=tmp_path)


def test_replay_checksum_survives_git_line_ending_normalization():
    settings = Settings()
    content = (ROOT / "data" / "replay.json").read_bytes()
    canonical = content.replace(b"\r\n", b"\n")
    assert content == canonical, "Hashed replay artifact must use LF on every platform"
    assert hashlib.sha256(canonical).hexdigest() == settings.manifest()["replay"]["sha256"]


def test_corrupted_cache_is_rejected(tmp_path):
    settings = copied(tmp_path)
    with (tmp_path / "replay.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(SourceError) as caught:
        load_replay(settings)
    assert caught.value.code == "replay_hash_mismatch"


def test_cache_cannot_be_attached_to_a_different_original_version(tmp_path):
    settings = copied(tmp_path)
    entry = settings.manifest()["sources"][0]
    entry["sha256"] = hashlib.sha256(b"different report").hexdigest()
    with pytest.raises(SourceError) as caught:
        extracted(settings, "pdf", entry)
    assert caught.value.code == "replay_source_mismatch"


async def test_clean_checkout_uses_all_three_evidence_types_without_network(tmp_path, monkeypatch):
    settings = copied(tmp_path)
    assert not (tmp_path / "raw").exists()
    network = AsyncMock(side_effect=AssertionError("demo must not download"))
    for module in ("news", "pdf", "price"):
        monkeypatch.setattr(f"mining_brief.providers.{module}.download", network)
    entry = settings.manifest()["sources"][0]
    news = await NewsProvider(settings).fetch_article(entry["url"])
    pdf = await PDFProvider(settings).extract_resources(entry["url"])
    price = await PriceProvider(settings).get_price("lithium", "2021-09-08")
    assert news["meta"]["evidence_origin"] == "verified_extraction_cache"
    assert pdf["data"]["document_hash"] == entry["sha256"]
    assert price["data"]["observation_date"] == "2021-09-08"
    network.assert_not_awaited()


async def test_live_never_uses_demo_price_when_feed_is_missing(monkeypatch):
    for name in ("MINING_PRICE_FILE", "MINING_PRICE_URL", "MINING_PRICE_CONTRACT"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SourceError) as caught:
        await PriceProvider(Settings(mode="live")).points("lithium")
    assert caught.value.code == "price_not_configured"

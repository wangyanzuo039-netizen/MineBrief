from unittest.mock import AsyncMock

import httpx
import pytest

from mining_brief.config import Settings
from mining_brief.network import SourceError
from mining_brief.providers.news import NewsProvider


async def test_rss_fallback_keeps_source_id_for_agent(monkeypatch):
    provider = NewsProvider(Settings(mode="live"))
    url = "https://news.google.com/rss/articles/example"
    provider.discovered[url] = {
        "id": "news-example",
        "url": url,
        "title": "Pilbara update",
        "publisher": "Example",
        "published_at": "2026-10-08",
        "summary": "Public RSS summary",
    }
    monkeypatch.setattr(
        "mining_brief.providers.news.download", AsyncMock(return_value=b"<html>JS required</html>")
    )
    response = await provider.fetch_article(url)
    assert response["status"] == "partial"
    assert response["data"]["source_id"] == response["sources"][0]["source_id"]
    assert response["data"]["text"] == "Public RSS summary"


@pytest.mark.parametrize(
    "failure", [httpx.ReadTimeout("timeout"), SourceError("unsafe_url", "blocked redirect")]
)
async def test_failed_fulltext_keeps_cached_summary_without_bypassing_policy(monkeypatch, failure):
    provider = NewsProvider(Settings(mode="live"))
    url = "https://news.google.com/rss/articles/example"
    provider.discovered[url] = {
        "id": "news-example",
        "url": url,
        "title": "Pilbara update",
        "publisher": "Example",
        "published_at": "2026-10-08",
        "summary": "Public RSS summary",
    }
    downloader = AsyncMock(side_effect=failure)
    monkeypatch.setattr("mining_brief.providers.news.download", downloader)
    response = await provider.fetch_article(url)
    assert response["status"] == "partial"
    assert response["data"]["text"] == "Public RSS summary"
    assert response["sources"][0]["source_id"] == "news-example"
    assert downloader.await_count == 1
    assert response["warnings"]


async def test_failed_fulltext_without_cached_evidence_stays_an_error(monkeypatch):
    provider = NewsProvider(Settings(mode="live"))
    monkeypatch.setattr(
        "mining_brief.providers.news.download", AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    )
    with pytest.raises(httpx.ReadTimeout):
        await provider.fetch_article("https://news.google.com/rss/articles/unknown")

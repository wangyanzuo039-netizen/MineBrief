from __future__ import annotations

import hashlib
from calendar import timegm
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import feedparser
import httpx
import pymupdf
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from mining_brief.config import Settings
from mining_brief.data import load_original
from mining_brief.network import SourceError, download
from mining_brief.schemas import Source, result


def matches_entity(query: str, text: str) -> bool:
    query = query.casefold()
    text = text.casefold()
    aliases = ("pilbara", "pilgangoora", "皮尔巴拉", "pls")
    if any(alias in query for alias in aliases):
        return any(alias in text for alias in aliases)
    return all(token in text for token in query.split())


class NewsProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.discovered: dict[str, dict[str, Any]] = {}

    async def search(self, query: str, days: int) -> dict[str, Any]:
        if not query.strip() or len(query) > 200 or not 1 <= days <= 90:
            raise SourceError("invalid_query", "query 长度 1–200；days 范围 1–90")
        end = date.fromisoformat(self.settings.as_of)
        start = end - timedelta(days=days - 1)
        items: list[dict[str, Any]] = []
        if self.settings.mode == "demo":
            manifest = self.settings.manifest()
            for entry in manifest["sources"]:
                if entry["id"] not in manifest["demo_news_ids"]:
                    continue
                published = date.fromisoformat(entry["published_at"])
                if start <= published <= end and matches_entity(query, entry["title"] + " Pilbara"):
                    items.append(
                        {
                            "id": entry["id"],
                            "title": entry["title"],
                            "url": entry["url"],
                            "published_at": published.isoformat(),
                            "publisher": entry["publisher"],
                            "summary": "发行人公开公告，调用 fetch_article 读取原文。",
                            "content_type": "issuer_announcement_pdf",
                        }
                    )
        else:
            params = urlencode(
                {
                    "q": f"{query} after:{start.isoformat()} before:{(end + timedelta(days=1)).isoformat()}",
                    "hl": "en-AU",
                    "gl": "AU",
                    "ceid": "AU:en",
                }
            )
            content = await download("https://news.google.com/rss/search?" + params, self.settings)
            feed = feedparser.parse(content)
            for item in feed.entries:
                published_parsed = item.get("published_parsed")
                if not published_parsed:
                    continue
                published = datetime.fromtimestamp(timegm(published_parsed), UTC).date()
                title = str(item.get("title", ""))
                if not start <= published <= end or not matches_entity(query, title):
                    continue
                url = str(item.get("link", ""))
                record = {
                    "id": "news-" + hashlib.sha256(url.encode()).hexdigest()[:12],
                    "title": title,
                    "url": url,
                    "published_at": published.isoformat(),
                    "publisher": str(item.get("source", {}).get("title", "Google News RSS")),
                    "summary": BeautifulSoup(str(item.get("summary", "")), "html.parser").get_text(
                        " ", strip=True
                    ),
                    "content_type": "rss_summary",
                }
                items.append(record)
                self.discovered[url] = record
        items = sorted(
            {item["url"]: item for item in items}.values(),
            key=lambda item: item["published_at"],
            reverse=True,
        )[:5]
        return result(
            {"articles": items, "window_start": start.isoformat(), "window_end": end.isoformat()},
            sources=[self.source(item) for item in items],
            status="ok" if items else "empty",
            warnings=[] if items else ["所查来源在指定窗口内未发现相关新闻"],
            mode=self.settings.mode,
        )

    @staticmethod
    def source(item: dict[str, Any]) -> Source:
        return Source(
            source_id=item["id"],
            url=HttpUrl(item["url"]),
            title=item["title"],
            publisher=item["publisher"],
            observation_date=date.fromisoformat(item["published_at"]),
        )

    def rss_summary(self, item: dict[str, Any], reason: str) -> dict[str, Any]:
        return result(
            {
                **item,
                "source_id": item["id"],
                "text": item["summary"],
                "content_type": "rss_summary",
            },
            sources=[self.source(item)],
            warnings=[reason],
            status="partial",
            mode=self.settings.mode,
        )

    async def fetch_article(self, url: str) -> dict[str, Any]:
        entry = next(
            (
                entry
                for entry in self.settings.manifest()["sources"]
                if entry["url"] == url and entry["kind"] == "pdf"
            ),
            None,
        )
        if entry:
            content = await load_original(self.settings, entry)
            with pymupdf.open(stream=content, filetype="pdf") as doc:  # type: ignore[no-untyped-call]
                text = "\n".join(doc[i].get_text() for i in range(min(3, len(doc))))
            item = {
                "id": entry["id"],
                "title": entry["title"],
                "publisher": entry["publisher"],
                "published_at": entry["published_at"],
                "url": url,
            }
            content_type = "issuer_announcement_pdf"
        else:
            if self.settings.mode == "demo":
                raise SourceError("unsupported_source", "历史模式未登记此文章 URL")
            cached = self.discovered.get(url)
            try:
                content = await download(url, self.settings)
            except (SourceError, httpx.HTTPError) as exc:
                if not cached or not str(cached.get("summary", "")).strip():
                    raise
                code = exc.code if isinstance(exc, SourceError) else type(exc).__name__
                return self.rss_summary(
                    cached, f"全文获取失败（{code}）；仅使用已取得的 RSS 摘要。"
                )
            soup = BeautifulSoup(content, "html.parser")
            article = soup.find("article") or soup.find("main")
            if not isinstance(article, Tag):
                if not cached or not str(cached.get("summary", "")).strip():
                    raise SourceError("content_unavailable", "正文不可用或需登录")
                return self.rss_summary(cached, "仅取得 RSS 摘要，未取得全文")
            for node in article.find_all(["script", "style", "nav", "footer"]):
                node.decompose()
            text = article.get_text(" ", strip=True)
            cached = self.discovered.get(url)
            if not cached:
                raise SourceError(
                    "publication_date_unknown", "请先通过 search 获取有发布日期的文章"
                )
            item = cached
            content_type = "article"
        if len(text.strip()) < 80:
            raise SourceError("content_unavailable", "来源正文过短")
        return result(
            {
                "title": item["title"],
                "text": text[:18000],
                "published_at": item["published_at"],
                "publisher": item["publisher"],
                "source_id": item["id"],
                "content_type": content_type,
                "content_hash": hashlib.sha256(content).hexdigest(),
            },
            sources=[self.source(item)],
            mode=self.settings.mode,
        )

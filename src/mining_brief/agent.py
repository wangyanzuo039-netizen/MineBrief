from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mining_brief.config import Settings
from mining_brief.mcp_client import MCPPool
from mining_brief.model import Narrative, Summary, generate_narrative
from mining_brief.render import render_brief
from mining_brief.schemas import result


def evidence_summary(article: dict[str, Any]) -> str:
    """Extract a short first highlight from fetched evidence, without inventing a summary."""
    highlight = article["text"].split("•", 1)[-1].split("•", 1)[0]
    words = re.sub(r"\s+", " ", highlight).strip().split()
    return "原文要点摘录：" + " ".join(words[:24]) + ("…" if len(words) > 24 else "")


def resolve_entity(query: str) -> str:
    if not any(
        alias in query.casefold() for alias in ("pilbara", "pilgangoora", "皮尔巴拉", "pls")
    ):
        raise ValueError("unsupported_entity: 首版支持 Pilbara / Pilgangoora")
    return "Pilgangoora"


async def run_agent(
    settings: Settings,
    query: str,
    output: Path,
    *,
    generation: str = "template",
    news_days: int = 30,
    price_days: int = 14,
) -> dict[str, Any]:
    entity = resolve_entity(query)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    directory = output / run_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest = settings.manifest()
    entry = next(
        entry
        for entry in manifest["sources"]
        if entry["id"]
        == manifest["demo_report_id" if settings.mode == "demo" else "live_report_id"]
    )
    async with asyncio.timeout(300), MCPPool(settings, directory / "trace.jsonl", run_id) as pool:
        evidence_gaps: list[str] = []
        search = await pool.call(
            "news", "search", {"query": "Pilbara Minerals Pilgangoora", "days": news_days}
        )
        fetched = []
        for item in search["data"].get("articles", [])[:3]:
            fetched.append(await pool.call("news", "fetch_article", {"url": item["url"]}))
        pdf = await pool.call("pdf", "extract_resources", {"pdf_url": entry["url"]})
        if max(entry["published_at"], entry.get("effective_date", "")) > settings.as_of:
            pdf = result(
                status="empty",
                warnings=["已登记资源报告晚于请求截止日，本次不引用；需要增加更早的报告。"],
                mode=settings.mode,
            )
            evidence_gaps.append("资源量板块缺失：登记报告晚于请求截止日，本次不引用。")
            pool.record(method="evidence/filter", status="excluded_future_report")
        price = await pool.call(
            "price", "get_price", {"commodity": "lithium_hydroxide", "date": settings.as_of}
        )
        trend = await pool.call(
            "price", "get_trend", {"commodity": "lithium_hydroxide", "days": price_days}
        )
        results = [search, *fetched, pdf, price, trend]
        articles = [
            item["data"]
            for item in fetched
            if item["status"] in {"ok", "partial"} and item["data"].get("text")
        ]
        sources_by_id: dict[str, dict[str, Any]] = {}
        for item in results:
            for source in item["sources"]:
                # Preserve PDF locator if article and report share the original URL.
                old = sources_by_id.get(source["source_id"], {})
                sources_by_id[source["source_id"]] = {**old, **source}
        sources = list(sources_by_id.values())
        warnings = [warning for item in results for warning in item["warnings"]]
        warnings.extend(
            item["error"]["code"] + ": " + item["error"]["message"]
            for item in results
            if item["error"]
        )
        narrative = Narrative(
            summaries=[
                Summary(
                    source_id=article["source_id"],
                    summary=evidence_summary(article),
                )
                for article in articles
            ],
            risks=[],
        )
        generation_mode = "template"
        model_meta: dict[str, Any] = {}
        if generation == "llm" and articles:
            try:
                narrative, model_meta = await generate_narrative(articles, sources)
                generation_mode = "llm"
                pool.record(method="model/generate", status="ok", **model_meta)
            except Exception as exc:
                warnings.append(
                    "模型生成未通过或不可用，已明确降级为证据模板：" + type(exc).__name__
                )
                pool.record(
                    method="model/generate", status="fallback", error_type=type(exc).__name__
                )
        if settings.mode == "demo":
            warnings.append(
                "历史回放；新闻和资源量按请求截止日筛选，价格为真实 LME 历史文件，未代表今日在线行情。"
            )
        complete = bool(
            articles
            and pdf["data"].get("resources")
            and price["data"].get("value")
            and trend["data"].get("percentage_change") is not None
            and all(item["status"] == "ok" for item in results)
        )
        if not complete:
            for name, item in zip(
                ("新闻", "资源量", "价格", "趋势"), (search, pdf, price, trend), strict=True
            ):
                if item["status"] not in {"ok", "partial"} or item["error"]:
                    code = item["error"]["code"] if item["error"] else item["status"]
                    evidence_gaps.append(
                        f"{name}证据缺失或不可用（{code}），本次结论不覆盖该部分。"
                    )
        status = "complete" if complete else "partial" if sources else "failed"
        brief = {
            "schema_version": "1.0",
            "run_id": run_id,
            "entity": entity,
            "query": query,
            "mode": settings.mode,
            "as_of": settings.as_of,
            "generated_at": datetime.now(UTC).isoformat(),
            "overall_status": status,
            "generation_mode": generation_mode,
            "model": model_meta,
            "articles": articles,
            "pdf": pdf,
            "price": price,
            "trend": trend,
            "narrative": narrative.model_dump(mode="json"),
            "sources": sources,
            "warnings": list(dict.fromkeys(warnings)),
            "evidence_gaps": list(dict.fromkeys(evidence_gaps)),
        }
        markdown = render_brief(brief)
        (directory / "brief.md").write_text(markdown, encoding="utf-8")
        # Evidence text retained locally; never secrets or model prompts.
        (directory / "brief.json").write_text(
            json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        pool.record(method="brief/render", status=status, generation_mode=generation_mode)
    return {
        "overall_status": status,
        "generation_mode": generation_mode,
        "run_id": run_id,
        "markdown": str((directory / "brief.md").resolve()),
        "evidence": str((directory / "brief.json").resolve()),
        "trace": str((directory / "trace.jsonl").resolve()),
    }

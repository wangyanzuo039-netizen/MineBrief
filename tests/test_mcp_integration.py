import json
from pathlib import Path

import pytest

from mining_brief.agent import run_agent
from mining_brief.config import Settings
from mining_brief.mcp_client import MCPPool

pytestmark = pytest.mark.integration


@pytest.fixture
def settings():
    return Settings()


async def test_three_stdio_servers_and_every_required_tool(settings, tmp_path):
    trace = tmp_path / "trace.jsonl"
    manifest = settings.manifest()
    ni = next(entry for entry in manifest["sources"] if entry["id"] == "zeus-ni43101")
    async with MCPPool(settings, trace, "test-protocol") as pool:
        news = await pool.call("news", "search", {"query": "Pilbara", "days": 30})
        assert len(news["data"]["articles"]) == 2
        fetched = await pool.call(
            "news", "fetch_article", {"url": news["data"]["articles"][0]["url"]}
        )
        assert fetched["data"]["content_type"] == "verified_original_excerpt"
        assert fetched["meta"]["evidence_origin"] == "verified_extraction_cache"
        pdf = await pool.call("pdf", "extract_resources", {"pdf_url": ni["url"]})
        assert pdf["data"]["reporting_standard"] == "NI 43-101"
        price = await pool.call(
            "price", "get_price", {"commodity": "lithium_hydroxide", "date": "2021-09-08"}
        )
        assert price["status"] == "ok"
        assert price["data"]["observation_date"] == "2021-09-08"
        trend = await pool.call(
            "price", "get_trend", {"commodity": "lithium_hydroxide", "days": 14}
        )
        assert trend["data"]["percentage_change"] is not None
        invalid = await pool.call("price", "get_trend", {"commodity": "lithium", "days": 0})
        assert invalid["error"]["code"] == "invalid_days"
        future = await pool.call(
            "price", "get_price", {"commodity": "lithium", "date": "2026-10-08"}
        )
        assert future["status"] == "empty"
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert {event["server"] for event in events} == {"news", "pdf", "price"}
    assert sum(event["method"] == "initialize+tools/list" for event in events) == 3


async def test_complete_agent_through_mcp_and_markdown_citations(settings, tmp_path):
    output = await run_agent(settings, "给我生成一份关于 Pilbara 锂矿的今日简报", tmp_path)
    assert output["overall_status"] == "complete"
    markdown = Path(output["markdown"]).read_text(encoding="utf-8")
    for section in ["新闻摘要", "资源量数据", "价格走势", "风险提示", "来源", "历史数据 Demo"]:
        assert section in markdown
    assert "188.7 Mt" in markdown
    assert "JORC 2012" in markdown
    assert "NI 43-101" not in markdown
    events = [
        json.loads(line) for line in Path(output["trace"]).read_text(encoding="utf-8").splitlines()
    ]
    assert {event["tool"] for event in events if "tool" in event} == {
        "search",
        "fetch_article",
        "extract_resources",
        "get_price",
        "get_trend",
    }


async def test_agent_excludes_report_published_after_cutoff(settings, tmp_path):
    configured = settings.model_copy(update={"as_of": "2021-09-01"})
    output = await run_agent(configured, "Pilbara 今日简报", tmp_path)
    assert output["overall_status"] == "partial"
    markdown = Path(output["markdown"]).read_text(encoding="utf-8")
    assert "晚于请求截止日" in markdown
    assert "188.7 Mt" not in markdown
    # 证据缺口必须写进日报正文，读者才能看出缺失原因。
    assert "缺口：资源量板块缺失" in markdown
    brief = json.loads(Path(output["evidence"]).read_text(encoding="utf-8"))
    assert any("资源量" in gap for gap in brief["evidence_gaps"])

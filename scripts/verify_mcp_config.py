"""Validate actual desktop-config commands through MCP, without a desktop account."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mining_brief.config import Settings
from mining_brief.schemas import ToolResult


async def verify(path: Path) -> dict:
    configuration = json.loads(path.read_text(encoding="utf-8-sig"))
    manifest = Settings().manifest()
    pdf = next(e for e in manifest["sources"] if e["id"] == manifest["ni_report_id"])
    news = next(e for e in manifest["sources"] if e["id"] == manifest["demo_news_ids"][0])
    checks = {
        "mining-news-mcp": [
            ("search", {"query": "Pilbara", "days": 30}),
            ("fetch_article", {"url": news["url"]}),
        ],
        "mineral-pdf-mcp": [("extract_resources", {"pdf_url": pdf["url"]})],
        "lme-price-mcp": [
            ("get_price", {"commodity": "lithium_hydroxide", "date": "2021-09-08"}),
            ("get_trend", {"commodity": "lithium_hydroxide", "days": 14}),
        ],
    }
    results = []
    for name, calls in checks.items():
        entry = configuration["mcpServers"][name]
        # No model credentials are passed to child services.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "APPDATA",
                "LOCALAPPDATA",
                "HOME",
                "LANG",
            }
        }
        environment.update(entry.get("env", {}))
        params = StdioServerParameters(
            command=entry["command"],
            args=entry.get("args", []),
            env=environment,
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=90)) as client,
        ):
            await client.initialize()
            tools = {t.name for t in (await client.list_tools()).tools}
            assert {tool for tool, _ in calls} <= tools, f"missing tools: {name}"
            for tool, arguments in calls:
                response = await client.call_tool(tool, arguments)
                assert not response.isError, f"protocol error: {name}/{tool}"
                payload = response.structuredContent
                if payload is None:
                    payload = json.loads(
                        "\n".join(c.text for c in response.content if c.type == "text")
                    )
                checked = ToolResult.model_validate(payload)
                assert checked.status == "ok", f"tool failure: {name}/{tool}"
                if tool == "extract_resources":
                    assert checked.data["reporting_standard"] == "NI 43-101"
                    assert {r["category"] for r in checked.data["resources"]} == {
                        "Indicated",
                        "Inferred",
                    }
                results.append(
                    {
                        "server": name,
                        "tool": tool,
                        "status": checked.status,
                        "source_ids": [s.source_id for s in checked.sources],
                    }
                )
    return {
        "passed": True,
        "transport": "stdio",
        "verification": "SDK with exact configuration commands",
        "checks": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("mcp-config.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/config-check.json"))
    args = parser.parse_args()
    response = asyncio.run(verify(args.config))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

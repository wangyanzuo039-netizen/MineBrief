from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from mining_brief.agent import run_agent
from mining_brief.config import ROOT, Settings
from mining_brief.data import prepare
from mining_brief.mcp_client import SERVERS, MCPPool
from mining_brief.replay import load_replay


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="通过三个 MCP 服务生成可追溯矿权日报")
    result.add_argument("--mode", choices=["demo", "live"], default="demo")
    result.add_argument("--as-of", help="分析截止日期 YYYY-MM-DD")
    result.add_argument("--query", default="给我生成一份关于 Pilbara 锂矿的今日简报")
    result.add_argument("--generation", choices=["template", "llm"], default="template")
    result.add_argument("--output", type=Path, default=ROOT / "outputs")
    result.add_argument("--strict", action="store_true", help="partial 也返回非零退出码")
    result.add_argument("--news-days", type=int, default=30)
    result.add_argument("--price-days", type=int, default=14)
    result.add_argument("--no-prepare", action="store_true", help="不检查/下载原始材料")
    sub = result.add_subparsers(dest="command")
    sub.add_parser("prepare", help="下载并校验公开原文；不提交外部原文到源码仓库")
    sub.add_parser("check", help="真实 MCP 调用所有规定工具并独立核验 NI 43-101")
    sub.add_parser("extract-ni", help="通过 MCP 抽取 Zeus NI 43-101 报告")
    config = sub.add_parser("mcp-config", help="生成桌面 MCP 配置")
    config.add_argument("--transport", choices=["docker", "local"], default="docker")
    config.add_argument("--destination", type=Path, default=ROOT / "mcp-config.local.json")
    return result


def desktop_config(transport: str) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    names = {"news": "mining-news-mcp", "pdf": "mineral-pdf-mcp", "price": "lme-price-mcp"}
    for server, (module, _) in SERVERS.items():
        if transport == "docker":
            entries[names[server]] = {
                "command": "docker",
                "args": [
                    "run",
                    "--rm",
                    "-i",
                    "--entrypoint",
                    "python",
                    "mining-brief:demo",
                    "-m",
                    module,
                ],
            }
        else:
            entries[names[server]] = {
                "command": sys.executable,
                "args": ["-m", module],
                "env": {
                    "MINING_MODE": "demo",
                    "MINING_AS_OF": "2021-09-08",
                    "MINING_DATA_DIR": str(ROOT / "data"),
                },
            }
    return {"mcpServers": entries}


async def execute(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    settings = Settings.from_env().model_copy(update={"mode": args.mode})
    if args.as_of:
        date.fromisoformat(args.as_of)
        settings.as_of = args.as_of
    elif args.mode == "live":
        from datetime import datetime
        from zoneinfo import ZoneInfo

        settings.as_of = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    if args.command == "mcp-config":
        args.destination.write_text(
            json.dumps(desktop_config(args.transport), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0, {"config": str(args.destination.resolve())}
    if args.command == "prepare":
        return 0, {"sources": await prepare(settings, include_live=True)}
    if settings.mode == "demo" and not args.no_prepare:
        load_replay(settings)
    if args.command in {"check", "extract-ni"}:
        manifest = settings.manifest()
        ni = next(entry for entry in manifest["sources"] if entry["id"] == manifest["ni_report_id"])
        output = args.output / (args.command + "-" + uuid.uuid4().hex[:8])
        async with MCPPool(settings, output / "trace.jsonl", output.name) as pool:
            calls = {}
            if args.command == "check":
                found = await pool.call("news", "search", {"query": "Pilbara", "days": 30})
                calls["search"] = found
                articles = found["data"].get("articles", [])
                if articles:
                    calls["fetch_article"] = await pool.call(
                        "news", "fetch_article", {"url": articles[0]["url"]}
                    )
                calls["get_price"] = await pool.call(
                    "price", "get_price", {"commodity": "lithium_hydroxide", "date": settings.as_of}
                )
                calls["get_trend"] = await pool.call(
                    "price", "get_trend", {"commodity": "lithium_hydroxide", "days": 14}
                )
            calls["extract_resources"] = await pool.call(
                "pdf", "extract_resources", {"pdf_url": ni["url"]}
            )
            ni_data = calls["extract_resources"]["data"]
            verified = ni_data.get("reporting_standard") == "NI 43-101" and {
                row["category"] for row in ni_data.get("resources", [])
            } == {"Indicated", "Inferred"}
            passed = (
                verified
                and all(value["status"] == "ok" for value in calls.values())
                and (args.command != "check" or len(calls) == 5)
            )
            target = output / "tool-results.json"
            target.write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding="utf-8")
        return (0 if passed else 1), {
            "passed": passed,
            "results": str(target.resolve()),
            "trace": str((output / "trace.jsonl").resolve()),
        }
    response = await run_agent(
        settings,
        args.query,
        args.output,
        generation=args.generation,
        news_days=args.news_days,
        price_days=args.price_days,
    )
    failed = response["overall_status"] == "failed" or (
        args.strict and response["overall_status"] != "complete"
    )
    return (1 if failed else 0), response


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    try:
        code, output = asyncio.run(execute(args))
    except KeyboardInterrupt:
        print("已停止，MCP 会话已关闭。", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception as exc:
        # HTTP exceptions may contain sensitive request details; expose only safe error classes.
        from mining_brief.network import SourceError

        message = str(exc) if isinstance(exc, (SourceError, ValueError)) else type(exc).__name__
        print(
            json.dumps(
                {"overall_status": "failed", "error_type": type(exc).__name__, "message": message},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()

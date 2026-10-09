"""校验 MCP 服务的工具契约：tools/list 必须与代码声明完全一致。

离线可用，不需要网络或原始文件；用于守住"服务只暴露规定工具"这条接口约定。
对应容器/真实验证：`docker compose -f compose.offline.yaml run --rm agent check`。
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mining_brief.config import ROOT
from mining_brief.mcp_client import SERVERS

EXPECTED = {name: required for name, (_, required) in SERVERS.items()}


async def inspect(name: str, module: str) -> dict[str, object]:
    parameters = StdioServerParameters(command=sys.executable, args=["-m", module], cwd=str(ROOT))
    async with (
        stdio_client(parameters) as (read, write),
        ClientSession(read, write, read_timeout_seconds=timedelta(seconds=60)) as client,
    ):
        await client.initialize()
        found = {tool.name for tool in (await client.list_tools()).tools}
    declared = EXPECTED[name]
    return {
        "server": name,
        "tools": sorted(found),
        "required": sorted(declared),
        "matches_contract": found == declared,
    }


def main() -> None:
    results = [asyncio.run(inspect(name, module)) for name, (module, _) in SERVERS.items()]
    passed = all(bool(item["matches_contract"]) for item in results)
    report = {"passed": passed, "transport": "stdio", "servers": results}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

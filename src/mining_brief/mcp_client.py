from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mining_brief.config import ROOT, Settings
from mining_brief.schemas import ToolResult

SERVERS = {
    "news": ("mining_brief.servers.news", {"search", "fetch_article"}),
    "pdf": ("mining_brief.servers.pdf", {"extract_resources"}),
    "price": ("mining_brief.servers.price", {"get_price", "get_trend"}),
}


class MCPPool:
    def __init__(self, settings: Settings, trace: Path, run_id: str) -> None:
        self.settings, self.trace, self.run_id = settings, trace, run_id
        self.stack = AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}

    def record(self, **fields: Any) -> None:
        event = {"run_id": self.run_id, "at": datetime.now(UTC).isoformat(), **fields}
        self.trace.parent.mkdir(parents=True, exist_ok=True)
        with self.trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    async def __aenter__(self) -> MCPPool:
        self.trace.parent.mkdir(parents=True, exist_ok=True)
        try:
            for name, (module, required) in SERVERS.items():
                # Only the Agent may receive model secrets; children get explicit runtime config.
                env = {
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
                env.update(
                    MINING_MODE=self.settings.mode,
                    MINING_AS_OF=self.settings.as_of,
                    MINING_DATA_DIR=str(self.settings.data_dir),
                    PYTHONIOENCODING="utf-8",
                    PYTHONUNBUFFERED="1",
                )
                for key in (
                    "MINING_PRICE_FILE",
                    "MINING_PRICE_CONTRACT",
                    "MINING_PRICE_SOURCE_URL",
                    "MINING_PRICE_URL",
                ):
                    if key in os.environ:
                        env[key] = os.environ[key]
                stderr_path = self.trace.parent / f"{name}.stderr.log"
                stderr = self.stack.enter_context(stderr_path.open("a", encoding="utf-8"))
                parameters = StdioServerParameters(
                    command=sys.executable, args=["-m", module], env=env, cwd=str(ROOT)
                )
                read, write = await self.stack.enter_async_context(
                    stdio_client(parameters, errlog=stderr)
                )
                session = await self.stack.enter_async_context(
                    ClientSession(read, write, read_timeout_seconds=timedelta(seconds=60))
                )
                await session.initialize()
                listed = await session.list_tools()
                found = {tool.name for tool in listed.tools}
                if not required <= found:
                    raise RuntimeError(f"{name}: missing tools {required - found}")
                self.sessions[name] = session
                self.record(
                    server=name,
                    method="initialize+tools/list",
                    tools=sorted(found),
                    status="ok",
                    transport="stdio",
                )
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(60):
                called = await self.sessions[server].call_tool(tool, arguments)
            if called.isError:
                raise RuntimeError("MCP tool returned protocol-level isError")
            payload = called.structuredContent
            if payload is None:
                blocks = [block.text for block in called.content if block.type == "text"]
                payload = json.loads("\n".join(blocks))
            checked = ToolResult.model_validate(payload).model_dump(mode="json")
            self.record(
                server=server,
                method="tools/call",
                tool=tool,
                arguments=arguments,
                status=checked["status"],
                duration_ms=round((time.perf_counter() - started) * 1000),
                source_ids=[source["source_id"] for source in checked["sources"]],
                error_code=checked["error"]["code"] if checked["error"] else None,
            )
            return checked
        except Exception as exc:
            self.record(
                server=server,
                method="tools/call",
                tool=tool,
                arguments=arguments,
                status="protocol_error",
                error_type=type(exc).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            raise

    async def __aexit__(self, *args: Any) -> None:
        await self.stack.aclose()

from typing import Any

from mcp.server.fastmcp import FastMCP

from mining_brief.config import Settings
from mining_brief.providers.news import NewsProvider
from mining_brief.servers.common import guarded

settings = Settings.from_env()
provider = NewsProvider(settings)
mcp = FastMCP("mining-news-mcp")


@mcp.tool()
async def search(query: str, days: int) -> dict[str, Any]:
    """Search mining news by entity and publication date within days of configured as_of."""
    return await guarded(lambda: provider.search(query, days), settings.mode)


@mcp.tool()
async def fetch_article(url: str) -> dict[str, Any]:
    """Fetch a public article or issuer PDF announcement, with date and source evidence."""
    return await guarded(lambda: provider.fetch_article(url), settings.mode)


if __name__ == "__main__":
    mcp.run(transport="stdio")

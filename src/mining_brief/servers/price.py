from typing import Any

from mcp.server.fastmcp import FastMCP

from mining_brief.config import Settings
from mining_brief.providers.price import PriceProvider
from mining_brief.servers.common import guarded

settings = Settings.from_env()
provider = PriceProvider(settings)
mcp = FastMCP("lme-price-mcp")


@mcp.tool()
async def get_price(commodity: str, date: str) -> dict[str, Any]:
    """Get a real LME quote at or before date with contract, units and provenance."""
    return await guarded(lambda: provider.get_price(commodity, date), settings.mode)


@mcp.tool()
async def get_trend(commodity: str, days: int) -> dict[str, Any]:
    """Calculate price changes from observed points of ONE fixed LME contract month."""
    return await guarded(lambda: provider.get_trend(commodity, days), settings.mode)


if __name__ == "__main__":
    mcp.run(transport="stdio")

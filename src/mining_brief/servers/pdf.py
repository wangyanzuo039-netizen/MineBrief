from typing import Any

from mcp.server.fastmcp import FastMCP

from mining_brief.config import Settings
from mining_brief.providers.pdf import PDFProvider
from mining_brief.servers.common import guarded

settings = Settings.from_env()
provider = PDFProvider(settings)
mcp = FastMCP("mineral-pdf-mcp")


@mcp.tool()
async def extract_resources(pdf_url: str) -> dict[str, Any]:
    """Parse original NI 43-101 / JORC PDFs into Indicated/Inferred resources with units and pages."""
    return await guarded(lambda: provider.extract_resources(pdf_url), settings.mode)


if __name__ == "__main__":
    mcp.run(transport="stdio")

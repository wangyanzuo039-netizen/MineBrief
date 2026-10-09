from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    url: HttpUrl
    title: str
    publisher: str
    observation_date: date | None = None
    page_number: int | None = Field(default=None, ge=1)


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ToolResult(BaseModel):
    schema_version: str = "1.0"
    status: Literal["ok", "partial", "empty", "error"] = "ok"
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: ToolError | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ResourceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["Measured", "Indicated", "Inferred", "Measured and Indicated"]
    category_raw: str
    ore_tonnage_value: Decimal
    ore_tonnage_unit: Literal["Mt", "kt", "t"]
    grade_value: Decimal
    grade_unit: str
    commodity: str
    contained_metal_value: Decimal | None = None
    contained_metal_unit: str | None = None
    basis: str
    cutoff: str | None = None
    page_number: int = Field(ge=1)
    evidence_text: str
    verification_status: str = "parsed_from_original"


class PricePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_date: date
    value: Decimal = Field(ge=0)
    currency: str = "USD"
    unit: str
    instrument: str
    price_type: str
    contract_month: str
    provider: str = "LME"
    source_url: HttpUrl


def result(
    data: dict[str, Any] | None = None,
    *,
    sources: list[Source] | None = None,
    warnings: list[str] | None = None,
    status: Literal["ok", "partial", "empty", "error"] = "ok",
    mode: str = "demo",
) -> dict[str, Any]:
    return ToolResult(
        status=status,
        data=data or {},
        sources=sources or [],
        warnings=warnings or [],
        meta={"mode": mode, "fetched_at": datetime.now(UTC).isoformat()},
    ).model_dump(mode="json")


def failure(code: str, message: str, *, mode: str, retryable: bool = False) -> dict[str, Any]:
    return ToolResult(
        status="error",
        error=ToolError(code=code, message=message, retryable=retryable),
        meta={"mode": mode, "fetched_at": datetime.now(UTC).isoformat()},
    ).model_dump(mode="json")

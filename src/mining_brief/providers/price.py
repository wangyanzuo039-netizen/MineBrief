from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl
from pydantic import HttpUrl

from mining_brief.config import Settings
from mining_brief.data import verify
from mining_brief.network import SourceError, original_path
from mining_brief.schemas import PricePoint, Source, result


def parse_workbook(content: bytes, contract: str, source_url: str) -> list[PricePoint]:
    """Map rolling M01..M15 to ONE fixed delivery month, avoiding roll distortion."""
    delivery = date.fromisoformat(contract + "-01")
    points: list[PricePoint] = []
    book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheet = book["LH"]
        rows = sheet.iter_rows(values_only=True)
        header = next(rows)
        if header[0] != "USD/mt":
            raise SourceError("price_schema_changed", "行情单位不是预期 USD/mt")
        for row in rows:
            if not isinstance(row[0], datetime):
                continue
            day = row[0].date()
            month_index = (delivery.year - day.year) * 12 + delivery.month - day.month + 1
            if not 1 <= month_index <= 15:
                continue
            if header[month_index] != f"M{month_index:02d}":
                raise SourceError("price_schema_changed", "行情合约列发生变化")
            raw = row[month_index]
            if raw is None:
                continue
            points.append(
                PricePoint(
                    observation_date=day,
                    value=Decimal(str(raw)),
                    unit="USD/mt",
                    instrument="LME Lithium Hydroxide CIF (Fastmarkets MB) / LH",
                    price_type="daily_closing_price",
                    contract_month=contract,
                    source_url=HttpUrl(source_url),
                )
            )
    finally:
        book.close()
    ordered = sorted(points, key=lambda point: point.observation_date)
    if len({point.observation_date for point in ordered}) != len(ordered):
        raise SourceError("duplicate_price_date", "行情存在重复日期")
    return ordered


def calculate_trend(points: list[PricePoint]) -> tuple[Decimal | None, Decimal | None]:
    signatures = {
        (p.instrument, p.price_type, p.contract_month, p.currency, p.unit) for p in points
    }
    if len(signatures) > 1:
        raise SourceError("mixed_price_series", "禁止混合商品、合约、单位或报价口径")
    if len(points) < 2 or points[0].value == 0:
        return None, None
    change = points[-1].value - points[0].value
    return change, (change / points[0].value * 100).quantize(Decimal("0.0001"))


class PriceProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def points(self, commodity: str) -> list[PricePoint]:
        if commodity.lower() not in {"lithium_hydroxide", "lithium", "锂", "氢氧化锂"}:
            raise SourceError("unsupported_commodity", "支持 lithium_hydroxide")
        entry = self.settings.manifest()["price"]
        local = original_path(self.settings, entry)
        if self.settings.mode == "demo":
            if not local.exists():
                raise SourceError("missing_data", "请先运行 mining-brief prepare 下载原始行情")
            content = local.read_bytes()
            verify(content, entry)
            contract = entry["contract_month"]
        else:
            import os

            configured = os.getenv("MINING_PRICE_FILE")
            if not configured:
                raise SourceError(
                    "price_not_configured",
                    "live 需要 MINING_PRICE_FILE 与 MINING_PRICE_CONTRACT；演示历史文件不会冒充今日行情",
                )
            contract = os.getenv("MINING_PRICE_CONTRACT", "")
            content = Path(configured).read_bytes()
        import os

        url = (
            entry["url"]
            if self.settings.mode == "demo"
            else os.getenv(
                "MINING_PRICE_SOURCE_URL",
                "https://www.lme.com/market-data/reports-and-data/historical-data-for-cash-settled-futures",
            )
        )
        return parse_workbook(content, contract, url)

    async def get_price(self, commodity: str, requested: str) -> dict[str, Any]:
        day = date.fromisoformat(requested)
        available = [p for p in await self.points(commodity) if p.observation_date <= day]
        if not available or (day - available[-1].observation_date).days > 7:
            return result(
                status="empty", warnings=["请求日前七天内没有有效报价"], mode=self.settings.mode
            )
        point = available[-1]
        data = point.model_dump(mode="json")
        data.update(requested_date=requested, is_stale=point.observation_date != day)
        return result(
            data,
            sources=[self.source(point)],
            warnings=["采用前一有效报价"] if data["is_stale"] else [],
            mode=self.settings.mode,
        )

    @staticmethod
    def source(point: PricePoint) -> Source:
        return Source(
            source_id="lme-lh",
            url=point.source_url,
            title="LME LH historical daily closing prices",
            publisher="London Metal Exchange",
            observation_date=point.observation_date,
        )

    async def get_trend(self, commodity: str, days: int) -> dict[str, Any]:
        if not 2 <= days <= 90:
            raise SourceError("invalid_days", "days 必须为 2–90")
        end = date.fromisoformat(self.settings.as_of)
        start = end - timedelta(days=days - 1)
        available = await self.points(commodity)
        points = [p for p in available if start <= p.observation_date <= end]
        change, percentage = calculate_trend(points)
        truncated = bool(
            points
            and (
                (points[0].observation_date - start).days > 7
                or (end - points[-1].observation_date).days > 7
            )
        )
        missing = percentage is None or truncated
        warnings = ["至少需要两个有效点且首值非零才能计算趋势"] if percentage is None else []
        if truncated:
            warnings.append("请求窗口边界超过七天没有报价，趋势仅代表实际披露区间；未插值补齐。")
        data = {
            "points": [p.model_dump(mode="json") for p in points],
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "first_date": points[0].observation_date.isoformat() if points else None,
            "last_date": points[-1].observation_date.isoformat() if points else None,
            "absolute_change": str(change) if change is not None else None,
            "percentage_change": str(percentage) if percentage is not None else None,
            "coverage": {
                "requested_calendar_days": days,
                "observations": len(points),
                "interpolated": False,
                "boundary_gap_exceeds_seven_days": truncated,
            },
        }
        return result(
            data,
            sources=[self.source(points[-1])] if points else [],
            status="partial" if missing else "ok",
            warnings=warnings,
            mode=self.settings.mode,
        )

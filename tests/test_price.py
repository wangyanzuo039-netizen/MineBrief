import io
from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pytest

from mining_brief.config import Settings
from mining_brief.network import SourceError
from mining_brief.providers.price import PriceProvider, calculate_trend, parse_workbook


def workbook(rows):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "LH"
    sheet.append(["USD/mt", *[f"M{i:02d}" for i in range(1, 16)]])
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def test_fixed_delivery_month_prevents_false_roll_change():
    data = workbook(
        [
            [datetime(2021, 8, 31), 900, 100, *([500] * 13)],
            [datetime(2021, 9, 1), 110, 999, *([500] * 13)],
        ]
    )
    points = parse_workbook(data, "2021-09", "https://www.lme.com/test.xlsx")
    assert [p.value for p in points] == [Decimal("100"), Decimal("110")]
    assert calculate_trend(points) == (Decimal("10"), Decimal("10.0000"))


def test_mixed_contracts_are_rejected():
    points = parse_workbook(
        workbook([[datetime(2021, 9, 1), *([100] * 15)]]),
        "2021-09",
        "https://www.lme.com/test.xlsx",
    )
    with pytest.raises(SourceError, match="禁止混合"):
        calculate_trend(
            [
                points[0],
                points[0].model_copy(
                    update={"contract_month": "2021-10", "observation_date": date(2021, 9, 2)}
                ),
            ]
        )


def test_zero_base_and_single_observation_do_not_invent_trend():
    points = parse_workbook(
        workbook([[datetime(2021, 9, 1), *([0] * 15)], [datetime(2021, 9, 2), *([10] * 15)]]),
        "2021-09",
        "https://www.lme.com/test.xlsx",
    )
    assert calculate_trend(points) == (None, None)
    assert calculate_trend(points[:1]) == (None, None)


@pytest.mark.parametrize("days,values", [(90, [100, 110]), (14, [0, 110])])
async def test_incomplete_window_or_zero_base_is_partial(monkeypatch, days, values):
    points = parse_workbook(
        workbook(
            [
                [datetime(2021, 9, 7), *([values[0]] * 15)],
                [datetime(2021, 9, 8), *([values[1]] * 15)],
            ]
        ),
        "2021-09",
        "https://www.lme.com/test.xlsx",
    )
    provider = PriceProvider(Settings())

    async def supplied(_commodity):
        return points

    monkeypatch.setattr(provider, "points", supplied)
    response = await provider.get_trend("lithium", days)
    assert response["status"] == "partial"
    assert response["warnings"]

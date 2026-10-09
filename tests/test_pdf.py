import pymupdf
import pytest

from mining_brief.config import ROOT
from mining_brief.network import SourceError
from mining_brief.providers.pdf import matches_effective_date, parse_resources


def original(name):
    path = ROOT / "data/raw" / name
    if not path.exists():
        pytest.skip("run mining-brief prepare to download original evidence")
    return path.read_bytes()


def synthetic_zeus(effective_text: str) -> bytes:
    """构造只含摘要关键词的合成报告，用于验证日期校验不依赖真实文件。"""
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Zeus Lithium Project NI 43-101 Technical Report")
        page.insert_text((72, 90), "Effective Date " + effective_text)
        page.insert_text(
            (72, 108), "Table 1-1: Mineral Resource Estimate 525 ppm Lithium Indicated"
        )
        return document.tobytes()


@pytest.mark.parametrize(
    "expression,expected,accepted",
    [
        ("June 2021", "2021-06-30", True),
        ("June 2021", "2021-06-29", False),
        ("May 15, 2024", "2024-05-15", True),
        ("15 May 2024", "2024-05-15", True),
        ("May 15, 2024", "2030-05-15", False),
        ("not a date", "2024-05-15", False),
    ],
)
def test_effective_date_expression_must_match_registered_metadata(expression, expected, accepted):
    assert matches_effective_date(expression, expected) is accepted


def test_pdf_with_unverified_effective_date_is_rejected_instead_of_reusing_metadata():
    with pytest.raises(SourceError) as caught:
        parse_resources(synthetic_zeus("May 15, 2030"))
    assert caught.value.code == "unverified_effective_date"


def test_pdf_with_matching_effective_date_passes_the_version_gate():
    with pytest.raises(SourceError) as caught:
        parse_resources(synthetic_zeus("May 15, 2024"))
    # 日期校验通过后才会走到表格抽取，因此这里应是取表失败而不是版本校验失败。
    assert caught.value.code == "resource_table_not_found"


def test_invalid_pdf_returns_error():
    with pytest.raises(SourceError, match="不是 PDF"):
        parse_resources(b"not a pdf")


def test_parser_extracts_categories_from_authored_jorc_fixture():
    # Synthetic numbers only: this file is a parser test, never briefing evidence.
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Pilgangoora JORC depleted to end of June 2021")
        page.insert_text((72, 100), "Table 1 Category")
        page.insert_text((72, 120), "Indicated 10 1.1 2 110000 4 5")
        page.insert_text((72, 140), "Inferred 20 1.2 2 240000 4 5")
        data = parse_resources(doc.tobytes())
    rows = {row["category"]: row for row in data["resources"]}
    assert rows["Indicated"]["ore_tonnage_value"] == "10"
    assert rows["Inferred"]["contained_metal_value"] == "240000"
    assert data["effective_date"] == "2021-06-30"


def test_ni_parser_extracts_only_total_rows_from_authored_table_fixture():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((60, 70), "Zeus Lithium Project NI 43-101 Technical Report")
        page.insert_text((60, 90), "Effective Date May 15, 2024")
        page.insert_text((60, 110), "Table 1-1: 525 ppm Lithium Indicated")
        xs, ys = [60, 130, 210, 290, 370, 450, 530], [150, 180, 210, 240, 270]
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[-1]))
        for y in ys:
            page.draw_line((xs[0], y), (xs[-1], y))
        cells = [
            ["Zone", "Category", "Mt", "ppm", "kt Li", "LCE"],
            ["Upper", "Indicated", "99", "99", "99", "99"],
            ["Total", "Indicated", "2", "3", "4", "5"],
            ["", "Inferred", "6", "7", "8", "9"],
        ]
        for row, values in enumerate(cells):
            for column, value in enumerate(values):
                page.insert_text((xs[column] + 5, ys[row] + 18), value, fontsize=9)
        data = parse_resources(doc.tobytes())
    assert len(data["resources"]) == 2
    assert [row["ore_tonnage_value"] for row in data["resources"]] == ["2", "6"]


@pytest.mark.live
def test_pilgangoora_original_preserves_jorc_and_page_evidence():
    data = parse_resources(original("pilgangoora_20210906.pdf"))
    assert data["reporting_standard"] == "JORC 2012"
    rows = {row["category"]: row for row in data["resources"]}
    assert rows["Indicated"]["ore_tonnage_value"] == "188.7"
    assert rows["Inferred"]["ore_tonnage_value"] == "98.8"
    assert rows["Indicated"]["contained_metal_value"] == "2172000"
    assert rows["Indicated"]["page_number"] == 3
    assert rows["Indicated"]["contained_metal_unit"] == "t Li2O"


@pytest.mark.live
def test_ni43101_uses_total_table_and_does_not_sum_subzones():
    data = parse_resources(original("zeus_2024.pdf"))
    assert data["reporting_standard"] == "NI 43-101"
    rows = {row["category"]: row for row in data["resources"]}
    assert len(rows) == 2
    assert rows["Indicated"]["ore_tonnage_value"] == "586"
    assert rows["Inferred"]["ore_tonnage_value"] == "300"
    assert rows["Indicated"]["grade_unit"] == "ppm Li"
    assert rows["Indicated"]["page_number"] == 11
    assert data["warnings"]


@pytest.mark.live
def test_2025_pilgangoora_uses_total_including_stockpiles_once():
    data = parse_resources(original("pilbara_2025.pdf"))
    rows = {row["category"]: row for row in data["resources"]}
    assert rows["Indicated"]["ore_tonnage_value"] == "356"
    assert rows["Indicated"]["contained_metal_value"] == "4.6"
    assert rows["Inferred"]["ore_tonnage_value"] == "70"
    assert data["effective_date"] == "2025-03-31"

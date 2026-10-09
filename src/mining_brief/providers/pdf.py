from __future__ import annotations

import hashlib
import re
import sys
from calendar import monthrange
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
from typing import Any

import pymupdf
from pydantic import HttpUrl

from mining_brief.config import Settings
from mining_brief.data import load_original
from mining_brief.network import SourceError, download
from mining_brief.schemas import ResourceRow, Source, result

NUMBER = r"([\d,]+(?:\.\d+)?)"
MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}
DATE_EXPRESSION = re.compile(
    r"(?:(?P<day_first>\d{1,2})\s+(?P<month_first>[A-Z][a-z]+)\s+(?P<year_first>\d{4})"
    r"|(?P<month_second>[A-Z][a-z]+)\s+(?P<day_second>\d{1,2}),?\s+(?P<year_second>\d{4})"
    r"|(?P<month_only>[A-Z][a-z]+)\s+(?P<year_only>\d{4}))"
)

# 已人工核验的 Pilgangoora 披露版本：有效日期 -> 原文中自述该日期的表述。
# 2021 报告原文写 "depleted to end of June 2021"（月末），2025 报告写 "calculated as at 31 March 2025"。
VERIFIED_JORC_VERSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("2025-03-31", (r"calculated as at\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",)),
    ("2021-06-30", (r"depleted to (?:the )?end of\s+([A-Za-z]+\s+\d{4})",)),
)


def decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def matches_effective_date(expression: str, expected: str) -> bool:
    """比对原文日期表述与登记元数据；只有月-年时视为该月最后一天。"""
    wanted = date.fromisoformat(expected)
    match = DATE_EXPRESSION.fullmatch(expression.strip())
    if match is None:
        return False
    parts = match.groupdict()
    month_name = parts["month_first"] or parts["month_second"] or parts["month_only"]
    month = MONTHS.get(month_name or "")
    if month is None:
        return False
    year = int(parts["year_first"] or parts["year_second"] or parts["year_only"])
    if (year, month) != (wanted.year, wanted.month):
        return False
    raw_day = parts["day_first"] or parts["day_second"]
    if raw_day is None:
        return wanted.day == monthrange(wanted.year, wanted.month)[1]
    return int(raw_day) == wanted.day


def verify_effective_date(text: str, expected: str, patterns: tuple[str, ...]) -> None:
    """原文自述的有效日期必须与登记元数据一致。

    登记日期是人工复核过的版本元数据。若原文换成新版本而 adapter 仍复用旧日期，
    报告会用旧日期标注新数字；因此无法在原文中确认时宁可报错，也不静默套用。
    """
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if matches_effective_date(match.group(1), expected):
                return
    raise SourceError(
        "unverified_effective_date",
        f"原文未出现与登记元数据一致的有效日期 {expected}，报告版本可能已变化；"
        "需人工核验后更新 adapter，不套用旧元数据",
    )


def parse_resources(content: bytes) -> dict[str, Any]:
    if not content.startswith(b"%PDF-"):
        raise SourceError("invalid_pdf", "输入不是 PDF")
    try:
        document: Any = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:
        raise SourceError("invalid_pdf", "PDF 无法打开") from exc
    with document:
        if document.is_encrypted or len(document) > 300 or len(document) == 0:
            raise SourceError("unsupported_pdf", "加密、空文件或超过 300 页的 PDF 不支持")
        texts = [page.get_text() for page in document]
        if not any(text.strip() for text in texts):
            raise SourceError("needs_ocr", "扫描 PDF 需要 OCR")
        whole = "\n".join(texts)
        rows: list[ResourceRow] = []
        warnings: list[str] = []
        if "Zeus" in whole and "NI 43-101" in whole:
            project, standard, effective = "Zeus Lithium Project", "NI 43-101", "2024-05-15"
            verify_effective_date(
                whole,
                effective,
                (r"Effective Date\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",),
            )
            for page, text in zip(document, texts, strict=True):
                if (
                    "Table 1-1:" not in text
                    or "525 ppm Lithium" not in text
                    or "Indicated" not in text
                ):
                    continue
                for table in page.find_tables().tables:
                    zone = ""
                    for cells in table.extract():
                        if len(cells) != 6:
                            continue
                        zone = cells[0] or zone
                        category = cells[1]
                        if zone == "Total" and category in {"Indicated", "Inferred"}:
                            evidence = " | ".join(cell or "" for cell in cells)
                            rows.append(
                                ResourceRow(
                                    category=category,
                                    category_raw=category,
                                    ore_tonnage_value=decimal(cells[2]),
                                    ore_tonnage_unit="Mt",
                                    grade_value=decimal(cells[3]),
                                    grade_unit="ppm Li",
                                    commodity="Li",
                                    contained_metal_value=decimal(cells[4]),
                                    contained_metal_unit="kt Li",
                                    basis="Total; dry tonnage; Table 1-1",
                                    cutoff="525 ppm Li",
                                    page_number=page.number + 1,
                                    evidence_text=evidence,
                                )
                            )
                if rows:
                    break
            warnings.append(
                "报告摘要表与结论段存在数值差异；此处按 Table 1-1 原表抽取，不混合两套数字。LCE 与含锂量分别披露，本结果使用含锂量。"
            )
        elif "Pilgangoora" in whole and "JORC" in whole:
            project, standard = "Pilgangoora", "JORC 2012"
            for effective, patterns in VERIFIED_JORC_VERSIONS:
                try:
                    verify_effective_date(whole, effective, patterns)
                except SourceError:
                    continue
                is_2025 = effective.startswith("2025")
                break
            else:
                raise SourceError(
                    "unsupported_format",
                    "Pilgangoora 报告版本未核验（原文有效日期与已登记版本均不一致），未猜测有效日期",
                )
            for index, text in enumerate(texts):
                marker = "Table 1"
                if marker not in text or "Category" not in text or "Indicated" not in text:
                    continue
                if is_2025:
                    match = re.search(r"Pilgangoora\s+Measured\s+", text)
                    if not match:
                        continue
                    scope = "Measured\n" + text[match.end() :]
                else:
                    scope = text
                pattern = r"\b(Indicated|Inferred)\s+" + r"\s+".join([NUMBER] * 6)
                matches = list(re.finditer(pattern, scope))
                if len(matches) != 2:
                    continue
                for match in matches:
                    category, tonnes, grade, _ta, fourth, fifth, _sixth = match.groups()
                    contained = fifth if is_2025 else fourth
                    rows.append(
                        ResourceRow(
                            category="Indicated" if category == "Indicated" else "Inferred",
                            category_raw=category,
                            ore_tonnage_value=decimal(tonnes),
                            ore_tonnage_unit="Mt",
                            grade_value=decimal(grade),
                            grade_unit="% Li2O",
                            commodity="Li2O",
                            contained_metal_value=decimal(contained),
                            contained_metal_unit="Mt Li2O" if is_2025 else "t Li2O",
                            basis="Pilgangoora total including stockpiles"
                            if is_2025
                            else "All domains; depleted to June 2021",
                            cutoff="0.2% Li2O",
                            page_number=index + 1,
                            evidence_text=" ".join(match.group(0).split()),
                        )
                    )
                break
        else:
            raise SourceError(
                "unsupported_format",
                "首版支持已核验的 Pilgangoora 和 Zeus 报告格式；其他版式需增加 adapter",
            )
        if not rows:
            raise SourceError("resource_table_not_found", "未找到可核验资源量表，未猜测数字")
        return {
            "project": project,
            "reporting_standard": standard,
            "effective_date": effective,
            "document_hash": hashlib.sha256(content).hexdigest(),
            "page_count": len(document),
            "resources": [row.model_dump(mode="json") for row in rows],
            "warnings": warnings,
        }


class PDFProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def extract_resources(self, url: str) -> dict[str, Any]:
        entry = next(
            (
                entry
                for entry in self.settings.manifest()["sources"]
                if entry["url"] == url and entry["kind"] == "pdf"
            ),
            None,
        )
        if entry is None:
            if self.settings.mode == "demo":
                raise SourceError(
                    "unsupported_source", "历史模式只使用 manifest 中登记并核验的 PDF URL"
                )
            content = await download(url, self.settings)
            digest = hashlib.sha256(content).hexdigest()
            entry = next(
                (
                    item
                    for item in self.settings.manifest()["sources"]
                    if item["kind"] == "pdf" and item["sha256"] == digest
                ),
                None,
            )
            if entry is None:
                raise SourceError(
                    "unverified_pdf_version",
                    "此报告版本未核验；需要登记文件哈希并验证日期与表格 adapter 后再抽取。",
                )
        else:
            content = await load_original(self.settings, entry)
        # Third-party table extraction may print a layout hint. stdout is MCP wire data.
        with redirect_stdout(sys.stderr):
            parsed = parse_resources(content)
        warnings = parsed.pop("warnings")
        source = Source(
            source_id=entry["id"] if entry else "pdf-" + parsed["document_hash"][:10],
            url=HttpUrl(url),
            title=entry["title"] if entry else parsed["project"],
            publisher=entry["publisher"] if entry else "PDF issuer",
            observation_date=parsed["effective_date"],
            page_number=parsed["resources"][0]["page_number"],
        )
        return result(parsed, sources=[source], warnings=warnings, mode=self.settings.mode)

from __future__ import annotations

from typing import Any


def escape(value: Any) -> str:
    return (
        str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
    )


def render_brief(brief: dict[str, Any]) -> str:
    sources = brief["sources"]
    indices = {source["source_id"]: index for index, source in enumerate(sources, 1)}

    def cite(source_id: str) -> str:
        if source_id not in indices:
            raise ValueError("unknown citation")
        return f"[{indices[source_id]}]"

    mode_label = "历史数据 Demo（不是今日实时行情）" if brief["mode"] == "demo" else "当前日期运行"
    lines = [
        "# Pilbara 锂矿日报",
        "",
        f"> {mode_label} · 分析截止：{brief['as_of']} · 生成：{brief['generated_at']}",
        f"> 实体：Pilbara Minerals / PLS 的 Pilgangoora 项目 · 状态：{brief['overall_status']} · 生成方式：{brief['generation_mode']}",
        "",
        "## 新闻摘要",
        "",
    ]
    summaries = {item["source_id"]: item["summary"] for item in brief["narrative"]["summaries"]}
    if not brief["articles"]:
        lines.append("所查来源在指定窗口内未发现可用新闻正文。")
    for article in brief["articles"]:
        lines.append(
            f"- **{escape(article['title'])}**（{article['published_at']}）：{escape(summaries[article['source_id']])} {cite(article['source_id'])}"
        )
    lines.extend(["", "## 资源量数据", ""])
    pdf = brief["pdf"]
    if pdf["data"].get("resources"):
        data = pdf["data"]
        reference = cite(pdf["sources"][0]["source_id"])
        lines.extend(
            [
                f"项目：{data['project']}；标准：{data['reporting_standard']}；有效日期：{data['effective_date']}。{reference}",
                "",
                "资源量类别与 Ore Reserve 储量分别报告，以下为资源量。",
                "",
                "| 类别 | 矿石量 | 品位 | 披露含金属量 | 证据 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in data["resources"]:
            metal = (
                f"{row['contained_metal_value']} {row['contained_metal_unit']}"
                if row["contained_metal_value"] is not None
                else "未披露"
            )
            lines.append(
                f"| {row['category']} | {row['ore_tonnage_value']} {row['ore_tonnage_unit']} | {row['grade_value']} {row['grade_unit']} | {metal} | PDF 第 {row['page_number']} 页 {reference} |"
            )
        lines.append(
            f"\n口径：{escape(data['resources'][0]['basis'])}；截止品位：{escape(data['resources'][0]['cutoff'])}。{reference}"
        )
    else:
        lines.append("资源量资料缺失，详见数据说明。")
    lines.extend(["", "## 价格走势", ""])
    quote, trend = brief["price"]["data"], brief["trend"]["data"]
    if quote.get("value"):
        reference = cite(brief["price"]["sources"][0]["source_id"])
        lines.extend(
            [
                f"商品：{quote['instrument']}；报价：{quote['price_type']}；固定交割月份：{quote['contract_month']}。{reference}",
                "",
                f"最近有效报价：**{quote['value']} {quote['unit']}**，实际日期 **{quote['observation_date']}**，请求日期 {quote['requested_date']}。{reference}",
            ]
        )
    if trend.get("points"):
        reference = cite(brief["trend"]["sources"][0]["source_id"])
        lines.append(
            f"\n观察区间：{trend['first_date']} 至 {trend['last_date']}，共 {len(trend['points'])} 个真实点；绝对变化 {trend['absolute_change'] or '无法计算'}，涨跌 {trend['percentage_change'] if trend['percentage_change'] is not None else '无法计算'}%。{reference}"
        )
        lines.extend(["", "| 日期 | 收盘价（USD/mt） |", "| --- | --- |"])
        for point in trend["points"]:
            lines.append(f"| {point['observation_date']} | {point['value']} {reference} |")
        lines.append(f"\n氢氧化锂是相关下游商品指标，不等于该项目锂辉石精矿的销售价格。{reference}")
    elif not quote.get("value"):
        lines.append("价格或趋势缺失，未填入模拟报价。")
    lines.extend(["", "## 风险提示", ""])
    for risk in brief["narrative"]["risks"]:
        lines.append(f"- 分析：{escape(risk['text'])} {cite(risk['source_id'])}")
    if pdf["sources"]:
        lines.append(
            f"- 资源量来自注明日期的历史披露，不能视为当日更新或经济可采储量。{cite(pdf['sources'][0]['source_id'])}"
        )
    if brief["price"]["sources"]:
        lines.append(
            f"- 合约口径与矿山产品存在差异，报价日期及合约月份必须同时考虑。{cite(brief['price']['sources'][0]['source_id'])}"
        )
    lines.extend(["\n## 数据说明", ""])
    for gap in brief.get("evidence_gaps", []):
        lines.append(f"- 缺口：{escape(gap)}")
    lines.extend(f"- {escape(warning)}" for warning in brief["warnings"])
    if not brief["warnings"] and not brief.get("evidence_gaps"):
        lines.append("- 本次所选数据模式下三类证据均已取得。")
    lines.extend(["", "## 来源", ""])
    for index, source in enumerate(sources, 1):
        locator = f"；PDF 第 {source['page_number']} 页" if source.get("page_number") else ""
        lines.append(
            f"{index}. [{escape(source['title'])}]({source['url']}) — {escape(source['publisher'])}；资料日期：{source.get('observation_date') or '见原文'}{locator}"
        )
    return "\n".join(lines) + "\n"

from __future__ import annotations

from typing import Any, Iterable


MARKET_POSITION_LABELS = {
    "high": "明显高于市场",
    "slightly_high": "略高于市场",
    "competitive": "与市场基本持平",
    "below_market": "低于市场",
    "unknown": "暂无法判断",
    "excluded": "暂不纳入市场比较",
}

DATA_ORIGIN_LABELS = {
    "current_observed": "本次已采集",
    "carry_forward": "沿用最近一次有效价格",
    "carry_forward_last_observed": "沿用最近一次有效价格",
    "subscription_mode_unavailable": "当前暂无该计费方式报价",
    "missing_collection": "本次未采集到",
    "unknown": "数据状态待确认",
}

COMPARABILITY_LABELS = {
    "strong_match": "高可比配置",
    "adjusted_match": "近似可比配置",
    "weak_match": "可比性较弱",
    "unknown": "可比性待确认",
}

TOOL_LABELS = {
    "get_market_overview": "市场概览",
    "search_configs": "配置检索",
    "compare_configuration": "配置价格比较",
    "get_pairing_evidence": "竞品可比依据",
    "get_price_changes": "价格变化",
    "get_price_history": "价格趋势",
    "get_metric_definition": "指标说明",
    "simulate_price": "定价模拟",
}


def _n(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_number(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".")


def format_price(value: Any) -> str:
    number = _n(value)
    return "暂无" if number is None else _clean_number(number, 3)


def format_index(value: Any) -> str:
    number = _n(value)
    return "暂无" if number is None else _clean_number(number, 1)


def format_percent_ratio(value: Any, *, signed: bool = True) -> str:
    number = _n(value)
    if number is None:
        return "暂无"
    pct = number * 100
    prefix = "+" if signed and pct > 0 else ""
    return f"{prefix}{_clean_number(pct, 1)}%"


def duration_label(value: Any) -> str:
    number = _n(value)
    if number is None:
        return "购买周期未标注"
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number))}天"
    return f"{_clean_number(number, 3)}天"


def market_position_label(value: Any) -> str:
    key = str(value or "unknown")
    return MARKET_POSITION_LABELS.get(key, "暂无法判断")


def data_origin_label(value: Any) -> str:
    key = str(value or "unknown")
    return DATA_ORIGIN_LABELS.get(key, "数据状态待确认")


def comparability_label(value: Any) -> str:
    key = str(value or "unknown")
    return COMPARABILITY_LABELS.get(key, "可比性待确认")


def tool_label(value: Any) -> str:
    return TOOL_LABELS.get(str(value or ""), "分析工具")


def data_caveat(row: dict[str, Any]) -> str:
    origin = str(row.get("data_origin") or row.get("analysis_status") or row.get("price_source") or "unknown")
    if origin in {"carry_forward", "carry_forward_last_observed"}:
        return "本次未采集到该报价，当前展示的是最近一次有效采集价格；建议等待下一次真实采集后再做高风险调价决策。"
    if origin == "subscription_mode_unavailable":
        return "当前未获得该计费方式的有效报价，因此不应把该状态当作零价或正常在售价格。"
    if origin == "missing_collection":
        return "本次采集未获得该报价，当前信息不足以支持新的价格判断。"
    if origin == "current_observed":
        return "该价格来自本次有效采集，可作为当前市场比较的直接依据。"
    note = str(row.get("analysis_note") or "").strip()
    if note:
        return note
    return "当前数据状态未完全确认，建议结合证据明细判断。"


def relative_difference_text(index: Any) -> str:
    number = _n(index)
    if number is None:
        return "与市场中位水平的差异暂无法计算"
    delta = number - 100
    if abs(delta) < 0.05:
        return "与可比竞品中位水平基本一致"
    if delta > 0:
        return f"约高出可比竞品中位水平 {_clean_number(delta, 1)}%"
    return f"约低于可比竞品中位水平 {_clean_number(abs(delta), 1)}%"


def _config_name(row: dict[str, Any]) -> str:
    label = str(row.get("label") or "").strip()
    if label:
        return label
    parts = [
        str(row.get("product_model") or "").strip(),
        f"Android {row.get('android_version')}" if row.get("android_version") else "",
        str(row.get("cpu") or "").strip(),
        str(row.get("ram") or "").strip(),
        str(row.get("storage") or "").strip(),
    ]
    return " / ".join(part for part in parts if part) or "当前配置"


def render_market_brief(summary: dict[str, Any]) -> str:
    counts = summary.get("market_position_counts") or {}
    high = int(counts.get("high") or 0)
    slightly_high = int(counts.get("slightly_high") or 0)
    competitive = int(counts.get("competitive") or 0)
    below = int(counts.get("below_market") or 0)
    above = high + slightly_high
    rows_compared = int(summary.get("rows_compared") or (above + competitive + below))

    if rows_compared:
        overview = (
            f"当前共有 {rows_compared} 个可比价格组合：{above} 个高于市场水平"
            f"（其中 {high} 个明显偏高、{slightly_high} 个略高），{competitive} 个与市场基本持平，{below} 个低于市场。"
        )
        if below > above:
            overview += " 整体分布更偏向低于市场的一侧，但不同产品与购买周期之间仍存在明显分化。"
        elif above > below:
            overview += " 整体分布更偏向高于市场的一侧，建议优先检查高价配置。"
        else:
            overview += " 高于与低于市场的配置数量接近，整体呈分化状态。"
    else:
        overview = "当前没有足够的可比价格组合，暂时无法形成可靠的整体市场判断。"

    top_items = summary.get("top_attention") or []
    focus = "暂未发现需要优先处理的高价配置。"
    caveat = "当前简报仅使用已进入可比价格体系的数据。"
    if top_items:
        top = top_items[0]
        focus = (
            f"优先关注 {_config_name(top)}（{duration_label(top.get('duration_days'))}）。"
            f"当前价格 {format_price(top.get('ugphone_price'))}，可比竞品中位价 {format_price(top.get('competitor_median_price'))}，"
            f"{relative_difference_text(top.get('relative_index'))}，因此当前判断为“{market_position_label(top.get('market_position'))}”。"
        )
        caveat = data_caveat(top)

    if above:
        recommendation = "建议先查看明显高于或略高于市场的配置，再结合购买周期、配置可比度和最新采集状态判断是否需要调价。"
    elif rows_compared:
        recommendation = "当前没有明显的高价集中风险；可以继续观察价格变化，并结合促销策略判断低于市场的配置是否符合预期。"
    else:
        recommendation = "建议先补充有效采集和可比配置，再进行定价判断。"

    return (
        f"市场概况\n{overview}\n\n"
        f"重点关注\n{focus}\n\n"
        f"数据提示\n{caveat}\n\n"
        f"建议\n{recommendation}"
    )


def render_price_change(row: dict[str, Any]) -> str:
    platform = str(row.get("platform") or "该平台")
    model = str(row.get("product_model") or "").strip()
    subject = f"{platform} {model}".strip()
    pct = _n(row.get("price_change_pct"))
    current = format_price(row.get("current_price"))
    previous = format_price(row.get("previous_price"))
    if pct is None:
        movement = "发生了价格变化"
    elif pct > 0:
        movement = f"上涨 {format_percent_ratio(abs(pct), signed=False)}"
    elif pct < 0:
        movement = f"下降 {format_percent_ratio(abs(pct), signed=False)}"
    else:
        movement = "价格与上次一致"
    caveat = data_caveat({"data_origin": row.get("price_source")})
    return f"变化最明显的是 {subject}：价格由 {previous} 变为 {current}，{movement}。{caveat}"


def render_configuration_summary(row: dict[str, Any]) -> str:
    name = _config_name(row)
    period = duration_label(row.get("duration_days"))
    position = market_position_label(row.get("market_position"))
    diff = relative_difference_text(row.get("relative_index"))
    caveat = data_caveat(row)
    return (
        f"{name}（{period}）当前价格为 {format_price(row.get('ugphone_price'))}，"
        f"可比竞品中位价为 {format_price(row.get('competitor_median_price'))}；{diff}，当前处于“{position}”区间。"
        f" {caveat}"
    )


def _pairing_sentence(pairings: Iterable[dict[str, Any]]) -> str:
    included: list[str] = []
    excluded: list[str] = []
    for item in pairings:
        platform = str(item.get("platform") or "竞品")
        price = format_price(item.get("price"))
        compare = comparability_label(item.get("comparability_level"))
        text = f"{platform} {price}（{compare}）"
        if item.get("included_in_core_median") is False:
            excluded.append(text)
        else:
            included.append(text)
    pieces: list[str] = []
    if included:
        pieces.append("纳入核心比较的竞品包括 " + "、".join(included[:4]) + "。")
    if excluded:
        pieces.append("另有 " + "、".join(excluded[:3]) + " 未进入核心中位价计算。")
    return "".join(pieces) or "当前没有足够的竞品配对记录可供解释。"


def render_configuration_explanation(row: dict[str, Any], pairings: list[dict[str, Any]]) -> str:
    name = _config_name(row)
    period = duration_label(row.get("duration_days"))
    position = market_position_label(row.get("market_position"))
    diff = relative_difference_text(row.get("relative_index"))
    comparison = _pairing_sentence(pairings)
    caveat = data_caveat(row)
    return (
        f"为什么是“{position}”\n"
        f"{name}（{period}）当前价格为 {format_price(row.get('ugphone_price'))}，"
        f"可比竞品中位价约为 {format_price(row.get('competitor_median_price'))}，{diff}。"
        f"因此，按照当前价格区间规则，该配置被判断为“{position}”。\n\n"
        f"比较依据\n{comparison}\n\n"
        f"数据提示\n{caveat}"
    )


def render_what_if(result: dict[str, Any]) -> str:
    old_position = market_position_label(result.get("old_market_position"))
    new_position = market_position_label(result.get("new_market_position"))
    proposed = format_price(result.get("proposed_price"))
    median = format_price(result.get("competitor_median_price"))
    change = format_percent_ratio(result.get("price_change_from_current_pct"))
    new_diff = relative_difference_text(result.get("new_relative_index"))

    if old_position == new_position:
        transition = f"市场位置仍为“{new_position}”"
    else:
        transition = f"市场位置将从“{old_position}”变为“{new_position}”"

    lines = [
        f"如果将价格调整为 {proposed}，{transition}。",
        f"模拟后的价格{new_diff}；当前可比竞品中位价为 {median}。",
    ]
    if change != "暂无":
        lines.append(f"相对当前价格的调整幅度为 {change}。")
    ceiling = _n(result.get("price_to_competitive_ceiling"))
    if ceiling is not None:
        lines.append(f"按照当前规则，进入“与市场基本持平”区间的价格上限约为 {format_price(ceiling)}。")
    return " ".join(lines)

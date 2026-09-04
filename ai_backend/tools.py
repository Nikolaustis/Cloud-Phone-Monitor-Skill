from __future__ import annotations

import re
from typing import Any, Callable

from .store import ContextStore
from .presentation import (
    render_configuration_explanation,
    render_configuration_summary,
    render_market_brief,
    render_price_change,
)


def _n(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def market_position(index: float | None, thresholds: dict[str, Any] | None = None) -> str:
    if index is None:
        return "unknown"
    thresholds = thresholds or {}
    below_market_lt = _n(thresholds.get("below_market_lt")) or 90.0
    competitive_lte = _n(thresholds.get("competitive_lte")) or 105.0
    slightly_high_lte = _n(thresholds.get("slightly_high_lte")) or 115.0
    if index < below_market_lt:
        return "below_market"
    if index <= competitive_lte:
        return "competitive"
    if index <= slightly_high_lte:
        return "slightly_high"
    return "high"


def _evidence(source: str, row: dict[str, Any], field: str, value: Any, note: str = "") -> dict[str, Any]:
    return {
        "fact_id": str(row.get("fact_id") or ""),
        "source_file": source,
        "record_id": str(row.get("config_id") or row.get("field") or row.get("fact_id") or ""),
        "field": field,
        "value": value,
        "note": note,
    }


def attach_evidence_ids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (row.get("fact_id"), row.get("source_file"), row.get("record_id"), row.get("field"), str(row.get("value")))
        if key in seen:
            continue
        seen.add(key)
        item = dict(row)
        item["evidence_id"] = f"E{len(output) + 1}"
        output.append(item)
    return output


class PricingTools:
    def __init__(self, store: ContextStore):
        self.store = store

    def get_market_overview(self) -> dict[str, Any]:
        summary = self.store.market_summary
        anchor = {"fact_id": "market_summary", "config_id": "market"}
        evidence = [
            _evidence("market_summary.json", anchor, "market_position_counts", summary.get("market_position_counts")),
            _evidence("market_summary.json", anchor, "rows_compared", summary.get("rows_compared")),
        ]
        return {"result": summary, "evidence": evidence}

    def search_configs(
        self,
        query: str = "",
        product_model: str = "",
        duration_days: float | None = None,
        market_position_filter: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        q = query.lower().strip()
        model = product_model.lower().strip()
        output = []
        for row in self.store.configs:
            haystack = " ".join(str(row.get(key) or "") for key in ("config_id", "label", "product_model", "android_version", "cpu", "ram", "storage")).lower()
            if q and q not in haystack:
                continue
            if model and model not in str(row.get("product_model") or "").lower():
                continue
            if duration_days is not None and abs((_n(row.get("duration_days")) or -9999) - float(duration_days)) > 1e-9:
                continue
            if market_position_filter and row.get("market_position") != market_position_filter:
                continue
            output.append(row)
        output = output[: max(1, min(int(limit), 50))]
        evidence = [_evidence("config_index.json", row, "relative_index", row.get("relative_index"), str(row.get("label") or "")) for row in output]
        return {"result": output, "evidence": evidence}

    def compare_configuration(self, config_id: str, duration_days: float | None = None) -> dict[str, Any]:
        matches = [
            row for row in self.store.configs
            if str(row.get("config_id")) == str(config_id)
            and (duration_days is None or abs((_n(row.get("duration_days")) or -9999) - float(duration_days)) < 1e-9)
        ]
        evidence: list[dict[str, Any]] = []
        for row in matches:
            evidence.extend([
                _evidence("config_index.json", row, "ugphone_price", row.get("ugphone_price"), str(row.get("label") or "")),
                _evidence("config_index.json", row, "competitor_median_price", row.get("competitor_median_price")),
                _evidence("config_index.json", row, "relative_index", row.get("relative_index")),
                _evidence("config_index.json", row, "data_origin", row.get("data_origin"), row.get("analysis_note") or ""),
            ])
        return {"result": matches, "evidence": evidence}

    def get_pairing_evidence(self, config_id: str, duration_days: float | None = None, limit: int = 20) -> dict[str, Any]:
        rows = []
        for row in self.store.pairings:
            if str(row.get("config_id")) != str(config_id):
                continue
            if duration_days is not None and abs((_n(row.get("duration_days")) or -9999) - float(duration_days)) > 1e-9:
                continue
            rows.append(row)
        rows.sort(key=lambda r: (_n(r.get("similarity_score")) or 0), reverse=True)
        rows = rows[: max(1, min(int(limit), 50))]
        evidence = [_evidence("pairing_index.json", row, "comparability_level", row.get("comparability_level"), f"{row.get('platform')} price={row.get('price')}") for row in rows]
        return {"result": rows, "evidence": evidence}

    def get_price_changes(self, direction: str = "all", platform: str = "", limit: int = 20) -> dict[str, Any]:
        rows = []
        for row in self.store.changes:
            if platform and str(row.get("platform") or "").lower() != platform.lower():
                continue
            pct = _n(row.get("price_change_pct"))
            if direction == "up" and not (pct is not None and pct > 0):
                continue
            if direction == "down" and not (pct is not None and pct < 0):
                continue
            rows.append(row)
        rows.sort(key=lambda row: abs(_n(row.get("price_change_pct")) or 0), reverse=True)
        rows = rows[: max(1, min(int(limit), 50))]
        evidence = [_evidence("price_events.json", row, "price_change_pct", row.get("price_change_pct"), str(row.get("platform") or "")) for row in rows]
        return {"result": rows, "evidence": evidence}

    def get_price_history(self, config_id: str, duration_days: float | None = None, limit: int = 30) -> dict[str, Any]:
        rows = []
        for row in self.store.trends:
            if str(row.get("config_id")) != str(config_id):
                continue
            if duration_days is not None and abs((_n(row.get("duration_days")) or -9999) - float(duration_days)) > 1e-9:
                continue
            item = dict(row)
            points = item.get("points") or []
            if isinstance(points, list):
                item["points"] = points[-max(1, min(int(limit), 365)):]
            rows.append(item)
        evidence = [_evidence("trend_index.json", row, "points", row.get("points"), f"history for {row.get('config_id')}") for row in rows]
        return {"result": rows, "evidence": evidence}

    def get_metric_definition(self, query: str) -> dict[str, Any]:
        q = query.lower().strip()
        matches = []
        for row in self.store.metrics:
            haystack = " ".join(str(value) for value in row.values()).lower()
            tokens = [token for token in re.split(r"\s+", q) if token]
            if (q and q in haystack) or any(token in haystack for token in tokens):
                matches.append(row)
        matches = matches[:10]
        evidence = [_evidence("metric_dictionary.json", row, "definition", row.get("meaning") or row.get("calculation"), row.get("name_zh") or "") for row in matches]
        return {"result": matches, "evidence": evidence}

    def simulate_price(self, config_id: str, proposed_price: float, duration_days: float | None = None) -> dict[str, Any]:
        row = next((
            item for item in self.store.configs
            if str(item.get("config_id")) == str(config_id)
            and (duration_days is None or abs((_n(item.get("duration_days")) or -9999) - float(duration_days)) < 1e-9)
        ), None)
        if row is None:
            return {"result": {"found": False, "config_id": config_id}, "evidence": []}
        median = _n(row.get("competitor_median_price"))
        current_price = _n(row.get("ugphone_price"))
        old_index = _n(row.get("relative_index"))
        new_index = proposed_price / median * 100 if median not in (None, 0) else None
        thresholds = self.store.manifest.get("market_position_thresholds") or {}
        competitive_lte = _n(thresholds.get("competitive_lte")) or 105.0
        competitive_ceiling = median * competitive_lte / 100.0 if median is not None else None
        change_pct = (proposed_price / current_price - 1) if current_price not in (None, 0) else None
        result = {
            "found": True,
            "config_id": config_id,
            "label": row.get("label"),
            "proposed_price": proposed_price,
            "current_price": current_price,
            "competitor_median_price": median,
            "old_relative_index": old_index,
            "new_relative_index": new_index,
            "old_market_position": row.get("market_position") or market_position(old_index, thresholds),
            "new_market_position": market_position(new_index, thresholds),
            "price_to_competitive_ceiling": competitive_ceiling,
            "price_change_from_current_pct": change_pct,
            "data_origin": row.get("data_origin"),
        }
        evidence = [
            _evidence("config_index.json", row, "competitor_median_price", median, str(row.get("label") or "")),
            _evidence("config_index.json", row, "ugphone_price", current_price, f"origin={row.get('data_origin')}"),
        ]
        return {"result": result, "evidence": evidence}

    def registry(self) -> dict[str, Callable[..., dict[str, Any]]]:
        return {
            "get_market_overview": self.get_market_overview,
            "search_configs": self.search_configs,
            "compare_configuration": self.compare_configuration,
            "get_pairing_evidence": self.get_pairing_evidence,
            "get_price_changes": self.get_price_changes,
            "get_price_history": self.get_price_history,
            "get_metric_definition": self.get_metric_definition,
            "simulate_price": self.simulate_price,
        }

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        fn = self.registry().get(name)
        if fn is None:
            return {"result": {"error": f"unknown_tool:{name}"}, "evidence": []}
        return fn(**arguments)


def _function_tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
        },
    }


TOOL_DEFINITIONS = [
    _function_tool("get_market_overview", "Get market-position counts and top pricing attention items.", {}, []),
    _function_tool("search_configs", "Search normalized UgPhone comparable configurations.", {
        "query": {"type": "string"}, "product_model": {"type": "string"}, "duration_days": {"type": ["number", "null"]},
        "market_position_filter": {"type": "string", "enum": ["", "below_market", "competitive", "slightly_high", "high"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    }, ["query", "product_model", "duration_days", "market_position_filter", "limit"]),
    _function_tool("compare_configuration", "Get deterministic price comparison and data-origin evidence for one configuration.", {
        "config_id": {"type": "string"}, "duration_days": {"type": ["number", "null"]},
    }, ["config_id", "duration_days"]),
    _function_tool("get_pairing_evidence", "Get competitor pairing, similarity and comparability evidence for one configuration.", {
        "config_id": {"type": "string"}, "duration_days": {"type": ["number", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    }, ["config_id", "duration_days", "limit"]),
    _function_tool("get_price_changes", "Find largest current price increases or decreases.", {
        "direction": {"type": "string", "enum": ["all", "up", "down"]}, "platform": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    }, ["direction", "platform", "limit"]),
    _function_tool("get_price_history", "Get historical price points for one normalized configuration.", {
        "config_id": {"type": "string"}, "duration_days": {"type": ["number", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 365},
    }, ["config_id", "duration_days", "limit"]),
    _function_tool("get_metric_definition", "Look up metric meaning, calculation and caveats.", {"query": {"type": "string"}}, ["query"]),
    _function_tool("simulate_price", "Deterministically simulate a proposed UgPhone price and recompute relative index/market position.", {
        "config_id": {"type": "string"}, "proposed_price": {"type": "number", "exclusiveMinimum": 0}, "duration_days": {"type": ["number", "null"]},
    }, ["config_id", "proposed_price", "duration_days"]),
]


def _duration_from_question(question: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:天|day|days|d)", question, re.I)
    return float(match.group(1)) if match else None


def _model_from_question(question: str) -> str:
    match = re.search(r"\b(UVIP|GVIP|KVIP|MVIP|SVIP|XVIP)\b", question, re.I)
    return match.group(1).upper() if match else ""


def answer_question_local(tools: PricingTools, question: str) -> dict[str, Any]:
    low = question.lower()
    duration = _duration_from_question(question)
    model = _model_from_question(question)

    if any(key in low for key in ("市场", "概览", "整体", "summary", "brief")) and not model:
        payload = tools.get_market_overview()
        return {
            "answer": render_market_brief(payload["result"]),
            "intent": "get_market_overview",
            "confidence": "high",
            "facts": payload["result"],
            "evidence": attach_evidence_ids(payload["evidence"]),
            "tool_calls": ["get_market_overview"],
        }

    if any(key in low for key in ("涨价", "降价", "价格变化", "price change", "increase", "decrease")):
        direction = "down" if any(k in low for k in ("降", "decrease")) else "up" if any(k in low for k in ("涨", "increase")) else "all"
        payload = tools.get_price_changes(direction=direction, platform="", limit=10)
        rows = payload["result"]
        if not rows:
            return {"answer": "当前数据中没有符合条件的价格变化记录。", "intent": "get_price_changes", "confidence": "low", "facts": rows, "evidence": [], "tool_calls": ["get_price_changes"]}
        return {
            "answer": render_price_change(rows[0]),
            "intent": "get_price_changes",
            "confidence": "high",
            "facts": rows,
            "evidence": attach_evidence_ids(payload["evidence"]),
            "tool_calls": ["get_price_changes"],
        }

    if any(key in low for key in ("怎么计算", "指标", "relative index", "相对竞品指数", "相似度", "formula")):
        query = "config_similarity_score" if "相似度" in low else "ugphone_relative_index"
        payload = tools.get_metric_definition(query)
        rows = payload["result"]
        if rows:
            row = rows[0]
            return {
                "answer": f"{row.get('name_zh') or row.get('field')}：{row.get('meaning') or ''} 计算方法：{row.get('calculation') or ''}",
                "intent": "get_metric_definition",
                "confidence": "high",
                "facts": rows,
                "evidence": attach_evidence_ids(payload["evidence"]),
                "tool_calls": ["get_metric_definition"],
            }

    search = tools.search_configs(query=model, product_model=model, duration_days=duration, market_position_filter="", limit=10)
    rows = search["result"]
    if not rows:
        return {"answer": "没有在当前结构化数据中找到匹配配置。为避免误导，我不会根据不存在的数据猜测价格。", "intent": "abstain", "confidence": "high", "facts": [], "evidence": [], "tool_calls": ["search_configs"]}
    row = rows[0]
    config_id = str(row.get("config_id"))

    if any(key in low for key in ("为什么", "解释", "why", "证据", "可比")):
        compare = tools.compare_configuration(config_id, duration)
        pairings = tools.get_pairing_evidence(config_id, duration, 10)
        evidence = attach_evidence_ids(compare["evidence"] + pairings["evidence"])
        return {
            "answer": render_configuration_explanation(row, pairings["result"]),
            "intent": "explain_configuration",
            "confidence": "high",
            "facts": {"configuration": row, "pairings": pairings["result"]},
            "evidence": evidence,
            "tool_calls": ["search_configs", "compare_configuration", "get_pairing_evidence"],
        }

    if any(key in low for key in ("趋势", "历史", "trend", "history")):
        payload = tools.get_price_history(config_id, duration, 30)
        if payload["result"]:
            return {
                "answer": f"已找到 {row.get('label')}（{int(duration) if duration is not None and float(duration).is_integer() else duration or row.get('duration_days')}天）的历史价格序列。具体时间点可在“查看依据”中核对。",
                "intent": "get_price_history",
                "confidence": "high",
                "facts": payload["result"],
                "evidence": attach_evidence_ids(payload["evidence"]),
                "tool_calls": ["search_configs", "get_price_history"],
            }

    return {
        "answer": render_configuration_summary(row),
        "intent": "search_configs",
        "confidence": "high",
        "facts": rows,
        "evidence": attach_evidence_ids(search["evidence"]),
        "tool_calls": ["search_configs"],
    }

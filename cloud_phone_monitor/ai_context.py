from __future__ import annotations

import gzip
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

AI_CONTEXT_SCHEMA_VERSION = "ai-context-v2"
AI_CONTEXT_CONTRACT_VERSION = 2
CORE_MARKET_POSITIONS = {"below_market", "competitive", "slightly_high", "high"}
MARKET_POSITION_THRESHOLDS = {
    "below_market_lt": 90.0,
    "competitive_lte": 105.0,
    "slightly_high_lte": 115.0,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.suffix == ".gz":
            return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, gzip.BadGzipFile):
        return default


def _read_first(paths: Iterable[Path], default: Any) -> Any:
    for path in paths:
        if path.is_file():
            return _read_json(path, default)
    return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rows(payload: Any, preferred_keys: Iterable[str] = ("rows", "items", "changes", "data", "series")) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    values = [value for value in payload.values() if isinstance(value, dict)]
    return [
        value for value in values
        if any(k in value for k in ("platform", "current_price", "ug_config_id", "field", "config_id"))
    ]


def _duration_comparison_rows(payload: Any) -> list[dict[str, Any]]:
    """Return UgPhone configuration-duration rows from duration_price_comparison.json.

    The dashboard file is the canonical duration inventory.  Real exports store
    comparison records under ``buckets``; older/synthetic fixtures may contain
    platform-grain rows.  Only UgPhone/configuration rows are eligible so a
    competitor row can never become a selectable UgPhone configuration.
    """
    candidates: list[dict[str, Any]] = []
    if isinstance(payload, list):
        candidates.extend(row for row in payload if isinstance(row, dict))
    elif isinstance(payload, dict):
        buckets = payload.get("buckets")
        if isinstance(buckets, dict):
            for bucket_rows in buckets.values():
                if isinstance(bucket_rows, list):
                    candidates.extend(row for row in bucket_rows if isinstance(row, dict))
        other_rows = payload.get("other_rows")
        if isinstance(other_rows, list):
            candidates.extend(row for row in other_rows if isinstance(row, dict))

    output: list[dict[str, Any]] = []
    for row in candidates:
        has_ug_fields = any(
            key in row
            for key in (
                "ug_config_id",
                "ug_config",
                "ug_product_model",
                "ugphone_price",
                "competitors",
            )
        )
        is_ugphone_platform_row = str(row.get("platform") or "").strip().lower() == "ugphone"
        if has_ug_fields or is_ugphone_platform_row:
            output.append(row)
    return output


def _fact_id(kind: str, payload: dict[str, Any]) -> str:
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return f"{kind}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:18]}"


def _position_from_index(index: float | None) -> str:
    if index is None:
        return "unknown"
    if index < MARKET_POSITION_THRESHOLDS["below_market_lt"]:
        return "below_market"
    if index <= MARKET_POSITION_THRESHOLDS["competitive_lte"]:
        return "competitive"
    if index <= MARKET_POSITION_THRESHOLDS["slightly_high_lte"]:
        return "slightly_high"
    return "high"


def _competitor_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("competitors")
    if isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    output: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        price = _number(
            item.get("quality_adjusted_price")
            or item.get("quality_adjusted_price_30d")
            or item.get("raw_effective_price_30d")
            or item.get("current_price")
            or item.get("price")
        )
        normalized = {
            "platform": item.get("platform") or item.get("competitor_platform") or "unknown",
            "product_model": item.get("product_model") or item.get("competitor_product_model") or "",
            "config": item.get("config") or item.get("competitor_config") or "",
            "price": price,
            "similarity_score": _number(item.get("config_similarity_score")),
            "comparability_level": item.get("comparability_level") or "unknown",
            "included_in_core_median": bool(item.get("included_in_core_median")),
            "pairing_source": item.get("pairing_source") or "",
            "exclusion_reason": item.get("exclusion_reason") or "",
        }
        normalized["fact_id"] = _fact_id("pairing", normalized)
        output.append(normalized)
    return output


def _median_core_price(competitors: list[dict[str, Any]]) -> float | None:
    prices = [
        item["price"]
        for item in competitors
        if item.get("included_in_core_median") and _number(item.get("price")) is not None
    ]
    return float(statistics.median(prices)) if prices else None


def normalize_config_row(row: dict[str, Any]) -> dict[str, Any]:
    competitors = _competitor_rows(row)
    median = _number(
        row.get("competitor_median_price")
        or row.get("competitor_median_quality_adjusted_price")
        or row.get("competitor_median_quality_adjusted_price_30d")
    )
    if median is None:
        median = _median_core_price(competitors)
    ug_price = _number(
        row.get("ugphone_price")
        or row.get("ug_effective_price")
        or row.get("ug_effective_price_30d")
        or row.get("current_price")
    )
    relative_index = _number(row.get("ugphone_relative_index") or row.get("relative_index"))
    if relative_index is None and ug_price is not None and median not in (None, 0):
        relative_index = ug_price / median * 100
    position = row.get("market_position_label") or row.get("market_position") or _position_from_index(relative_index)
    if position not in CORE_MARKET_POSITIONS:
        position = _position_from_index(relative_index)

    config_id = str(row.get("ug_config_id") or row.get("config_id") or row.get("canonical_product_key") or row.get("id") or "")
    product_model = str(row.get("ug_product_model") or row.get("product_model") or "")
    android = str(row.get("ug_android_version") or row.get("android_version") or "")
    cpu = str(row.get("ug_cpu") or row.get("cpu") or "")
    ram = str(row.get("ug_ram") or row.get("ram") or "")
    storage = str(row.get("ug_storage") or row.get("storage") or "")
    duration = _number(row.get("duration_days") or row.get("duration_bucket") or row.get("actual_duration_days"))
    label = str(
        row.get("ug_config")
        or row.get("config")
        or " / ".join(part for part in (product_model, f"Android {android}" if android else "", cpu, ram, storage) if part)
    )
    normalized = {
        "config_id": config_id,
        "label": label,
        "product_model": product_model,
        "android_version": android,
        "cpu": cpu,
        "ram": ram,
        "storage": storage,
        "duration_days": duration,
        "ugphone_price": ug_price,
        "competitor_median_price": median,
        "relative_index": relative_index,
        "market_position": position,
        "confidence_level": row.get("confidence_level") or "unknown",
        "analysis_status": row.get("analysis_status") or "unknown",
        "data_origin": row.get("data_origin") or row.get("price_source") or "unknown",
        "availability_status": row.get("availability_status") or "unknown",
        "analysis_note": row.get("analysis_note") or row.get("confidence_notes") or "",
        "exclude_from_market_position": bool(row.get("exclude_from_market_position")),
        "competitors": competitors,
    }
    if not normalized["config_id"]:
        seed = {k: normalized[k] for k in ("product_model", "android_version", "cpu", "ram", "storage", "duration_days")}
        normalized["config_id"] = _fact_id("config_key", seed)
    fact_payload = {k: v for k, v in normalized.items() if k != "competitors"}
    normalized["fact_id"] = _fact_id("config", fact_payload)
    return normalized


def normalize_change_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "platform": row.get("platform") or "unknown",
        "config_id": row.get("config_id") or row.get("ug_config_id") or row.get("baseline_key") or "",
        "product_model": row.get("product_model") or row.get("ug_product_model") or "",
        "duration_days": _number(row.get("duration_days") or row.get("duration_bucket")),
        "current_price": _number(row.get("current_price")),
        "previous_price": _number(row.get("previous_price")),
        "price_change_pct": _number(row.get("price_change_pct")),
        "reason_code": row.get("reason_code") or "",
        "alert_level": row.get("alert_level") or "none",
        "price_source": row.get("price_source") or row.get("data_origin") or "unknown",
        "promotion_text_changed": bool(row.get("promotion_text_changed")),
        "observed_at": row.get("observed_at") or row.get("date") or row.get("current_date") or "",
    }
    normalized["fact_id"] = _fact_id("price_event", normalized)
    return normalized


def normalize_trend_row(row: dict[str, Any]) -> dict[str, Any] | None:
    config_id = str(row.get("config_id") or row.get("canonical_product_key") or row.get("series_id") or "")
    values = row.get("points") or row.get("values") or row.get("data") or []
    if not config_id and not values:
        return None
    normalized = {
        "config_id": config_id,
        "platform": row.get("platform") or "",
        "product_model": row.get("product_model") or "",
        "duration_days": _number(row.get("duration_days") or row.get("duration_bucket")),
        "points": values if isinstance(values, list) else [],
    }
    normalized["fact_id"] = _fact_id("trend", normalized)
    return normalized


def _config_richness(row: dict[str, Any]) -> int:
    return (
        (8 if _number(row.get("ugphone_price")) is not None else 0)
        + (4 if _number(row.get("competitor_median_price")) is not None else 0)
        + (2 if _number(row.get("relative_index")) is not None else 0)
        + min(len(row.get("competitors") or []), 4)
        + (1 if str(row.get("analysis_status") or "unknown") != "unknown" else 0)
    )


def _dedupe_configs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # A selectable entity is configuration + purchase period.  Price is a fact
    # about that entity, not part of its identity.  Keeping price in the key can
    # create duplicate selector rows when attention/pairing snapshots differ.
    positions: dict[tuple[Any, ...], int] = {}
    output: list[dict[str, Any]] = []
    for row in rows:
        key = (row.get("config_id"), row.get("duration_days"))
        if key not in positions:
            positions[key] = len(output)
            output.append(row)
            continue
        index = positions[key]
        if _config_richness(row) > _config_richness(output[index]):
            output[index] = row
    return output


@dataclass(slots=True)
class AIContextBuildResult:
    output_dir: Path
    files: dict[str, int]
    data_revision: str
    data_date: str


def build_ai_context(data_dir: Path, output_dir: Path | None = None) -> AIContextBuildResult:
    data_dir = data_dir.resolve()
    output_dir = (output_dir or data_dir / "ai").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    meta = _read_json(data_dir / "meta.json", {})
    overview = _read_json(data_dir / "frontend_price_overview.json", {})
    duration_comparison_raw = _read_json(data_dir / "duration_price_comparison.json", {})
    price_changes_raw = _read_json(data_dir / "price_change_tracking.json", [])
    pairing_raw = _read_json(data_dir / "pairing_matrix.json", [])
    metric_raw = _read_json(data_dir / "metric_definitions.json", [])
    trend_raw = _read_first((data_dir / "price_trends.json.gz", data_dir / "price_trends.json"), {})

    # Duration comparison is the canonical inventory for selector availability.
    # It must be ingested before attention/pairing subsets; otherwise Explain and
    # What-if only expose the few durations that happen to exist in those subsets.
    canonical_duration_rows = _duration_comparison_rows(duration_comparison_raw)
    candidate_rows: list[dict[str, Any]] = list(canonical_duration_rows)
    if isinstance(overview, dict):
        candidate_rows.extend(_rows(overview.get("attention_items", [])))
    candidate_rows.extend(_rows(pairing_raw))
    configs = _dedupe_configs([normalize_config_row(row) for row in candidate_rows])
    configs = [row for row in configs if row.get("config_id") or row.get("label")]

    # Fail closed if the AI selector index ever drops a configuration-duration
    # pair that exists in the canonical Dashboard duration inventory.  This is
    # the contract that prevents Explain/What-if from silently exposing only an
    # attention/pairing subset such as 1d + 180d.
    canonical_selector_keys = {
        (row.get("config_id"), row.get("duration_days"))
        for row in (normalize_config_row(item) for item in canonical_duration_rows)
        if row.get("config_id") and _number(row.get("duration_days")) not in (None, 0)
    }
    built_selector_keys = {
        (row.get("config_id"), row.get("duration_days"))
        for row in configs
        if row.get("config_id") and _number(row.get("duration_days")) not in (None, 0)
    }
    missing_selector_keys = sorted(canonical_selector_keys - built_selector_keys, key=lambda item: (str(item[0]), float(item[1] or 0)))
    if missing_selector_keys:
        preview = ", ".join(f"{config_id}@{duration}d" for config_id, duration in missing_selector_keys[:12])
        raise RuntimeError(f"AI selector inventory lost {len(missing_selector_keys)} canonical configuration-duration rows: {preview}")

    changes = [normalize_change_row(row) for row in _rows(price_changes_raw)]
    metrics: list[dict[str, Any]] = []
    for row in _rows(metric_raw):
        normalized = dict(row)
        normalized["fact_id"] = _fact_id("metric", normalized)
        metrics.append(normalized)

    trends: list[dict[str, Any]] = []
    for row in _rows(trend_raw):
        normalized = normalize_trend_row(row)
        if normalized:
            trends.append(normalized)

    position_counts = dict(overview.get("market_position_counts") or {}) if isinstance(overview, dict) else {}
    if not position_counts:
        for row in configs:
            position = row.get("market_position") or "unknown"
            position_counts[position] = int(position_counts.get(position, 0)) + 1

    priority = {"high": 0, "slightly_high": 1, "competitive": 2, "below_market": 3, "unknown": 4}
    top_attention = sorted(
        [row for row in configs if not row.get("exclude_from_market_position")],
        key=lambda row: (priority.get(str(row.get("market_position")), 9), -abs((_number(row.get("relative_index")) or 100) - 100)),
    )[:20]

    data_revision = str(meta.get("current_price_data_revision") or meta.get("data_revision") or "unknown")
    data_date = str(meta.get("last_run_date") or overview.get("updated_at") or meta.get("generated_at_utc") or "unknown")

    market_summary = {
        "schema_version": AI_CONTEXT_SCHEMA_VERSION,
        "generated_at_utc": _now_iso(),
        "data_date": data_date,
        "data_revision": data_revision,
        "rows_compared": overview.get("rows_compared") if isinstance(overview, dict) else len(configs),
        "market_position_counts": position_counts,
        "above_market_count": int(position_counts.get("high", 0)) + int(position_counts.get("slightly_high", 0)),
        "below_market_count": int(position_counts.get("below_market", 0)),
        "top_attention": top_attention,
        "data_quality_note": "Preserve data_origin/analysis_status. Carry-forward rows are not newly observed prices.",
    }

    pairing_index: list[dict[str, Any]] = []
    for config in configs:
        for competitor in config.get("competitors", []):
            item = {
                "config_id": config.get("config_id"),
                "config_fact_id": config.get("fact_id"),
                "ug_config": config.get("label"),
                "duration_days": config.get("duration_days"),
                **competitor,
            }
            item["fact_id"] = competitor.get("fact_id") or _fact_id("pairing", item)
            pairing_index.append(item)

    files: dict[str, Any] = {
        "market_summary.json": market_summary,
        "config_index.json": configs,
        "price_events.json": changes,
        "pairing_index.json": pairing_index,
        "trend_index.json": trends,
        "metric_dictionary.json": metrics,
        "question_examples.json": [
            "今天哪些 UgPhone 配置高于市场？",
            "为什么 KVIP 30天明显高于市场？",
            "最近有哪些明显涨价或降价？",
            "最近7天 KVIP 的价格趋势如何？",
            "UgPhone 相对竞品指数怎么计算？",
            "如果把某配置调到新的价格，市场位置会变成什么？",
        ],
    }
    counts: dict[str, int] = {}
    for name, payload in files.items():
        _write_json(output_dir / name, payload)
        counts[name] = len(payload) if isinstance(payload, list) else 1

    high_count = int(position_counts.get("high", 0))
    slightly_high_count = int(position_counts.get("slightly_high", 0))
    competitive_count = int(position_counts.get("competitive", 0))
    below_count = int(position_counts.get("below_market", 0))
    above_count = high_count + slightly_high_count
    brief_lines = [
        f"数据日期：{data_date}",
        f"当前共有 {market_summary.get('rows_compared') or len(configs)} 个可比价格组合。",
        f"其中 {above_count} 个高于市场水平（{high_count} 个明显偏高、{slightly_high_count} 个略高），{competitive_count} 个与市场基本持平，{below_count} 个低于市场。",
    ]
    if top_attention:
        first = top_attention[0]
        origin = str(first.get("data_origin") or "")
        origin_note = "本次已采集" if origin == "current_observed" else "当前使用最近一次有效采集价格" if origin in {"carry_forward", "carry_forward_last_observed"} else "数据状态需结合证据确认"
        duration_value = _number(first.get("duration_days"))
        duration_text = (str(int(round(duration_value))) if duration_value is not None and abs(duration_value - round(duration_value)) < 1e-9 else str(duration_value or "-"))
        brief_lines.append(
            f"优先关注：{first.get('label')} / {duration_text}天；相对价格指数 {first.get('relative_index')}，{origin_note}。"
        )
    (output_dir / "market_brief.txt").write_text("\n".join(brief_lines) + "\n", encoding="utf-8")
    counts["market_brief.txt"] = len(brief_lines)

    manifest = {
        "schema_version": AI_CONTEXT_SCHEMA_VERSION,
        "contract_version": AI_CONTEXT_CONTRACT_VERSION,
        "generated_at_utc": _now_iso(),
        "data_date": data_date,
        "data_revision": data_revision,
        "safe_data_only": bool(meta.get("safe_data_only", True)),
        "source": "dashboard_data",
        "files": counts,
        "market_position_thresholds": MARKET_POSITION_THRESHOLDS,
        "core_duration_buckets": duration_comparison_raw.get("core_buckets", []) if isinstance(duration_comparison_raw, dict) else [],
        "selector_inventory_count": len(canonical_selector_keys),
        "capabilities": [
            "market_brief",
            "structured_query",
            "evidence_grounding",
            "config_explain",
            "price_change_query",
            "price_trend_query",
            "pairing_evidence",
            "pricing_what_if",
        ],
    }
    _write_json(output_dir / "manifest.json", manifest)
    counts["manifest.json"] = 1
    return AIContextBuildResult(output_dir=output_dir, files=counts, data_revision=data_revision, data_date=data_date)
